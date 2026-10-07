"""凍結済み主比較を発話単位で集計し、診断改善と品質認定を分離する。"""
import json
import sys
import numpy as np
from budget import ROOT,RESULT,save,digest
from quality_gate import decide
sys.path.insert(0,str(ROOT.parent/'autonomous-speech-synthesis/src'))
from autonomous_speech_synthesis.evaluation import grouped_bootstrap

VARIANTS=['handwritten','reference_fitted','direct_non_neural','neural_control','distilled_non_neural']


def main():
    rows=json.loads((RESULT/'splits.json').read_text())['rows']
    values=[]
    for row in rows:
        fitted=json.loads((RESULT/'fitted'/row['id']/'summary.json').read_text())
        for name in VARIANTS:
            record=fitted['handwritten'] if name=='handwritten' else fitted['fit']['best'] if name=='reference_fitted' else json.loads((RESULT/'comparisons'/name/f'{row["id"]}.json').read_text())
            asr=json.loads((RESULT/'content'/name/f'{row["id"]}.json').read_text())
            if digest(ROOT/record['wav'])!=asr['wav_sha256']:
                raise ValueError('音響評価とASRの音声が一致しません')
            measured,target=record['measurement'],fitted['target']
            values.append({'id':row['id'],'split':row['split'],'variant':name,
                 'engineering_pass':record['evaluation']['E0_pass'],'objective':record['objective'],
                 'f0_absolute_log_error':float(abs(np.log(measured['f0_hz']/target['f0_hz']))),
                 'duration_absolute_log_error':float(abs(np.log(measured['active_seconds']/target['active_seconds']))),
                 'kana_errors':asr['errors'],'kana_characters':asr['characters'],'kana_cer':asr['kana_cer']})
    groups={}
    for split in ('development','selection','audit'):
        groups[split]={}
        for name in VARIANTS:
            r=[r for r in values if r['split']==split and r['variant']==name]
            groups[split][name]={'utterances':len(r),
                 'engineering_pass':all(x['engineering_pass'] for x in r),
                 'f0_mean_absolute_log_error':float(np.mean([x['f0_absolute_log_error'] for x in r])),
                 'duration_mean_absolute_log_error':float(np.mean([x['duration_absolute_log_error'] for x in r])),
                 'objective_mean':float(np.mean([x['objective'] for x in r])),
                 'kana_cer_micro':sum(x['kana_errors'] for x in r)/sum(x['kana_characters'] for x in r),
                 'kana_cer_macro':float(np.mean([x['kana_cer'] for x in r]))}
    audit=groups['audit']; contrasts={}
    for name in ('direct_non_neural','neural_control','distilled_non_neural'):
        a={r['id']:r for r in values if r['split']=='audit' and r['variant']==name}
        b={r['id']:r for r in values if r['split']=='audit' and r['variant']=='handwritten'}
        contrasts[name]={metric:grouped_bootstrap([a[k][metric]-b[k][metric] for k in sorted(a)],comparisons=3)
                         for metric in ('objective','kana_cer')}
        contrasts[name]['content_protection_pass']=audit[name]['kana_cer_micro']<=audit['handwritten']['kana_cer_micro']
    teacher={}
    for split in ('development','selection','audit'):
        records=[json.loads((RESULT/'content/teacher'/f'{r["id"]}.json').read_text()) for r in rows if r['split']==split]
        teacher[split]={'utterances':len(records),'kana_cer_micro':sum(r['errors'] for r in records)/sum(r['characters'] for r in records)}
    summary={'groups':groups,'teacher':teacher,'contrasts':contrasts,'rows':values,
             'independent_audit_utterances':6,'repeated_seeds_counted_as_independent':False,
             'model_selection_sha256':digest(RESULT/'model-selection.json'),
             'perception_qualified':False,'quality_goal_achieved':False,
             'limitations':['全体F0と長さだけを適合したため、調音・自然さの改善を直接証明しない',
                            '監査6文は小規模で、CIが広い場合に同等性を主張しない',
                            'かなCERはASR診断であり人間の明瞭度ではない'],
             'next_action':'内容保護を含めて移行時の損失を調べ、自然参照・別生成器対照・単独実行を監査する'}
    save(RESULT/'main-comparison-summary.json',summary)
    print(json.dumps({'audit':audit,'teacher':teacher['audit'],'content_protection':{k:v['content_protection_pass'] for k,v in contrasts.items()}},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
