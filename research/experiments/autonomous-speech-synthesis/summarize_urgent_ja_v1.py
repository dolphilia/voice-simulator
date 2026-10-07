#!/usr/bin/env python3
"""独立した話者を単位とし、公開評点と予測の順位・誤順位・不確実性を報告する。"""
import itertools
import sys
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,file_hash


def main():
    path=ROOT/'results/urgent-ja-v1';result=read(path/'evaluation.json');manifest=read(path/'manifest.json')
    rows=result['rows'];primary=[r for r in rows if r['kind']=='primary'];groups={}
    for r in primary:groups.setdefault(r['utterance_id'],[]).append(r)
    comparisons=[]
    for utterance,group in groups.items():
        valid=[r for r in group if r.get('prediction') is not None]
        if len(valid)!=6:
            comparisons.append({'utterance':utterance,'speaker':group[0]['speaker_id'],'status':'unavailable','missing':6-len(valid)});continue
        labels=np.array([r['mos'] for r in valid]);pred=np.array([r['prediction'] for r in valid])
        corr=float(spearmanr(labels,pred).statistic) if np.std(labels)>0 and np.std(pred)>0 else None
        pairs=[]
        for a,b in itertools.combinations(valid,2):
            delta=a['mos']-b['mos'];prediction=a['prediction']-b['prediction']
            pairs.append({'system_a':a['system_id'],'system_b':b['system_id'],'mos_delta':delta,'prediction_delta':prediction,
                          'label_tie':delta==0,'concordant':bool(delta*prediction>0) if delta!=0 else None})
        not_tied=[p for p in pairs if not p['label_tie']]
        comparisons.append({'utterance':utterance,'speaker':group[0]['speaker_id'],'status':'available','spearman':corr,
                            'pair_count':len(not_tied),'pair_agreement':sum(p['concordant'] for p in not_tied)/len(not_tied) if not_tied else None,
                            'mos_range':[float(min(labels)),float(max(labels))],'prediction_range':[float(min(pred)),float(max(pred))],
                            'pairs':pairs,'rating_count':[len(r['listener_scores']) for r in valid]})
    available=[r for r in comparisons if r['status']=='available' and r['spearman'] is not None and r['pair_agreement'] is not None]
    if len({r['speaker'] for r in available})!=len(available):raise ValueError('話者1人につき1発話の分割が崩れています')
    summary={};rng=np.random.default_rng(81203)
    for key in ('spearman','pair_agreement'):
        values=np.array([r[key] for r in available])
        boot=np.mean(rng.choice(values,size=(2000,len(values)),replace=True),axis=1) if len(values) else []
        summary[key]={'speaker_mean':float(values.mean()) if len(values) else None,'speaker_bootstrap_95ci':np.quantile(boot,[.025,.975]).tolist() if len(boot) else None,'speakers':len(values)}
    base={r['sample_id']:r for r in primary};repeat=[];seed=[]
    for r in rows:
        if r['kind'] not in ('repeat','seed7'):continue
        key=r['sample_id'].removesuffix('-repeat').removesuffix('-seed7');b=base[key]
        if r.get('prediction') is not None and b.get('prediction') is not None:
            (repeat if r['kind']=='repeat' else seed).append(r['prediction']-b['prediction'])
    checkpoint=read(path/'model-provenance.json')['weights_sha256']
    model_api=read(path/'model-api.json');data_api=read(path/'dataset-api.json')
    tree=read(path/'model-tree.json');official=next(r['lfs']['oid'] for r in tree if r['path']=='fold0_s42_best_model.pth')
    audit={'state':'diagnostic-only','E2_physical_speech_qualified':False,'promotion_allowed':False,'summary':summary,
           'coverage':{'selected_utterances':len(groups),'complete_valid_utterances':len(available),'primary_predictions':len(primary),'missing_predictions':sum(r.get('prediction') is None for r in rows),'all_predictions':len(rows)},
           'repeat_max_error':float(max(abs(np.array(repeat)))) if len(repeat)==6 else None,
           'seed7_deltas':seed,'repeat_coverage':len(repeat),'seed7_coverage':len(seed),'utterances':comparisons,
           'training_overlap':{'official_weight_hash_matches':checkpoint==official,'model_repository_modified':model_api.get('lastModified'),'dataset_repository_created':data_api.get('createdAt'),'public_source_datasets':['bvcc','sarulab','blizzard2008','blizzard2009','blizzard2010-EH1','blizzard2010-EH2','blizzard2010-ES1','blizzard2010-ES3','blizzard2011','somos'],
                               'urgent2026_listed_in_default_training_map':False,'full_training_identity_independence_verified':False,'reason':'公開の既定訓練集合表にはURGENT2026がない。重みと全訓練音声の対応、SSL元発話との重複は未検証。列挙の不在だけで独立性を断定しない。'},
           'limits':['日本語ラベル・日本語文字を含む発話を選択した。音声の全内容が日本語であることの人手検査なし','雑音除去音声の品質評点であり、物理合成の自然さへの転移は未検証','同じ発話内の6システムや15対を独立話者として数えない','個票に聴取者IDがないため聴取者単位の再標本化は未実施','この資料の結果から生成候補の合否閾値を事後設定しない'],
           'sources':{'dataset':'https://huggingface.co/datasets/urgent-challenge/urgent2026-sqa','revision':manifest['source_revision'],'model':'https://huggingface.co/sarulab-speech/UTMOSv2'},
           'source_sha256':file_hash(Path(__file__)),'evaluation_sha256':file_hash(path/'evaluation.json')}
    write_once(path/'qualification.json',audit)
    print({k:v for k,v in audit.items() if k not in ('utterances','training_overlap','limits','sources')})

if __name__=='__main__':main()
