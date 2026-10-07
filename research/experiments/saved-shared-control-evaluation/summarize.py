"""新旧診断を分けて内容・局所F0・干渉・蒸留損失を判定する。"""
import subprocess
import sys
import numpy as np
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest


def groups(rows):
    output={}
    for condition in ('neutral','challenge','both'):
        for group in ('all','short','long','group-0','group-1','group-2','group-3'):
            selected=[r for r in rows if (condition=='both' or r['condition']==condition) and
                (group=='all' or r['length']==group or group=='group-'+str(r['challenge_group']))]
            complete=[r for r in selected if r['status']=='completed'];errors=sum(r['errors'] for r in complete)
            native=sum(r['native_errors'] for r in complete);characters=sum(r['characters'] for r in complete)
            output[condition+'/'+group]={'expected':len(selected),'missing':len(selected)-len(complete),
                'independent_texts':len({r['text_id'] for r in selected}),'errors':errors,'native_errors':native,'characters':characters,
                'cer':errors/characters if characters else None,'native_cer':native/characters if characters else None,
                'non_worsening':bool(selected) and len(complete)==len(selected) and errors<=native}
    return output


def mse_groups(rows):
    output={}
    for condition in ('neutral','challenge'):
        for length in ('all','short','long'):
            selected=[r for r in rows if r['condition']==condition and (length=='all' or r['length']==length)]
            complete=[r for r in selected if r['wave_mse'] is not None and r['native_mse'] is not None]
            value=float(np.mean([r['wave_mse'] for r in complete])) if complete else None
            native=float(np.mean([r['native_mse'] for r in complete])) if complete else None
            output[condition+'/'+length]={'expected':len(selected),'missing':len(selected)-len(complete),'mean_mse':value,'native_mean_mse':native,
                'non_worsening':bool(selected) and len(complete)==len(selected) and value<=native,
                'strict_improvement':bool(selected) and len(complete)==len(selected) and value<native}
    return output


def tests():
    rows=[{'text_id':str(i),'condition':c,'length':'short' if i<4 else 'long','challenge_group':i%4,
        'status':'completed','errors':1,'native_errors':1,'characters':5} for i in range(8) for c in ('neutral','challenge')]
    assert len(groups(rows))==21 and all(g['non_worsening'] for g in groups(rows).values())
    bad=[dict(r) for r in rows];bad[0]['status']='missing';assert not all(g['non_worsening'] for g in groups(bad).values())
    bad=[dict(r) for r in rows];bad[0]['errors']=2;assert not all(g['non_worsening'] for g in groups(bad).values())
    assert not any(g['non_worsening'] for g in groups([]).values())
    m=[{**r,'wave_mse':.5,'native_mse':1.} for r in rows];assert all(g['non_worsening'] and g['strict_improvement'] for g in mse_groups(m).values())
    m[0]['wave_mse']=None;assert not all(g['non_worsening'] for g in mse_groups(m).values())
    return {'twenty_one_content_groups':True,'missing_worse_empty_rejected':True,'mse_missing_rejected':True,'render_calls':0,'ai_calls':0}


def main():
    with LocalBudget().job('audit','42群の内容保護・実波形F0・全体干渉・学生への損失を集計',2000000):
        p=read(RESULT/'protocol.json');manifest=read(RESULT/'render-manifest.json');records={r['id']:read(REPO/r['source_record']) for r in manifest['rows']}
        engineering={};content={};transfer=[]
        for variant in p['variants'][1:]:
            pairs=[];mse=[]
            for row in p['selection_rows']+p['rows']:
                for condition in row['requests']:
                    r=records[row['id']+'/'+condition+'/'+variant];n=records[row['id']+'/'+condition+'/native']
                    valid=r['status']==n['status']=='completed';differences={}
                    if valid:
                        for f in ('f0_hz','dio_f0_hz','active_seconds'):
                            a,z=r['measurement'].get(f),n['measurement'].get(f)
                            differences[f]=a/z-1 if a is not None and z is not None and z>0 else None
                    protected=valid and all(differences.get(f) is not None and abs(differences[f])<=limit for f,limit in [('f0_hz',.05),('dio_f0_hz',.05),('active_seconds',.03)])
                    checks={'completed':valid,'E0':valid and r['E0_pass'] and n['E0_pass'],
                        'internal':valid and r['internal_unchanged'] and n['internal_unchanged'],
                        'support':valid and r['support_complete'] and n['support_complete'],'global_control':protected}
                    pairs.append({'text_id':row['id'],'split':row['split'],'condition':condition,'relative_to_native':differences,
                        'checks':checks,'passed':all(checks.values()),'missing_support':r.get('missing_support')})
                    if row['split']=='selection':mse.append({'text_id':row['id'],'length':row['length'],'condition':condition,'wave_mse':r.get('wave_mse'),'native_mse':n.get('wave_mse')})
            acoustic=mse_groups(mse)
            engineering[variant]={'pairs':pairs,'all_waveform_controls_protected':all(r['passed'] for r in pairs),'selection_mse_groups':acoustic,
                'selection_acoustic_supported':all(r['non_worsening'] for r in acoustic.values()) and all(acoustic[c+'/all']['strict_improvement'] for c in ('neutral','challenge'))}
            content[variant]={}
            for engine in ('whisper','reazon'):
                subsets={}
                for split,rows in [('selection',p['selection_rows']),('diagnostic',p['rows'])]:
                    pairs=[]
                    for row in rows:
                        for condition in row['requests']:
                            a=read(RESULT/'asr'/engine/(row['id']+'/'+condition+'/'+variant+'.json'))
                            n=read(RESULT/'asr'/engine/(row['id']+'/'+condition+'/native.json'))
                            pair={'text_id':row['id'],'length':row['length'],'challenge_group':row['challenge_group'],'condition':condition,'status':'missing'}
                            if a['status']==n['status']=='completed':
                                for record in (a,n):
                                    assert record['protocol_sha256']==digest(RESULT/'protocol.json') and digest(REPO/record['wav'])==record['wav_sha256']
                                assert a['reference_kana']==n['reference_kana'] and a['characters']==n['characters']
                                pair.update(status='completed',errors=a['errors'],native_errors=n['errors'],characters=a['characters'],
                                    hypothesis=a['hypothesis'],native_hypothesis=n['hypothesis'])
                            pairs.append(pair)
                    grouped=groups(pairs);subsets[split]={'pairs':pairs,'groups':grouped,'all_groups_non_worsening':all(r['non_worsening'] for r in grouped.values())}
                content[variant][engine]=subsets
        for row in p['selection_rows']+p['rows']:
            for condition in row['requests']:
                neural=records[row['id']+'/'+condition+'/neural'];student=records[row['id']+'/'+condition+'/distilled_non_neural'];direct=records[row['id']+'/'+condition+'/direct_non_neural']
                valid=all(r['status']=='completed' and r['support_complete'] for r in (neural,student,direct))
                transfer.append({'text_id':row['id'],'split':row['split'],'condition':condition,'support_complete':valid,
                    'nn_student_shape_mse':float(np.mean((np.asarray(neural['wave_shape'])-np.asarray(student['wave_shape']))**2)) if valid else None,
                    'direct_student_shape_mse':float(np.mean((np.asarray(direct['wave_shape'])-np.asarray(student['wave_shape']))**2)) if valid else None,
                    'nn_target_mse':neural.get('wave_mse'),'student_target_mse':student.get('wave_mse'),'direct_target_mse':direct.get('wave_mse')})
        from dictionary_diagnostic import main as dictionary_main
        dictionary_main()
        qualifications={}
        for variant in p['variants'][1:]:
            c=all(content[variant][engine][split]['all_groups_non_worsening'] for engine in ('whisper','reazon') for split in ('selection','diagnostic'))
            e=engineering[variant];qualifications[variant]={'content_supported':c,'waveform_controls_supported':e['all_waveform_controls_protected'],
                'selection_acoustic_supported':e['selection_acoustic_supported'],'research_qualified':c and e['all_waveform_controls_protected'] and e['selection_acoustic_supported']}
        save(RESULT/'summary.json',{'engineering':engineering,'content':content,'transfer':transfer,'qualifications':qualifications,
            'training_mse':read(RESULT/'model-comparison.json')['training_mse'],'runtime_independence_passed':read(RESULT/'runtime-audit.json')['passed'],
            'any_non_neural_research_qualified':any(qualifications[v]['research_qualified'] for v in ('direct_non_neural','distilled_non_neural')),
            'quality_certified':False,'all_requirements_met':False,'independent_final_confirmation':False,'no_optimization_after_asr':True,
            'limitations':['新8文は教師なしの内容・工学診断。自然さの独立正解ではない。','旧12文は研究診断へ使用済み。最終確認群ではない。',
                'DIO/HMM/教師境界の日本語測定器資格は未達。','小標本のかな保護は統計的非劣性ではない。'],
            'unresolved':['局所閉鎖・開放・摩擦・声質','日本語非ニューラル知覚資格','独立最終品質確認']})
        print(qualifications,flush=True)

if __name__=='__main__':main()
