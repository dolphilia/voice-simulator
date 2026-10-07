"""改訂研究版の工学結果と、未実施の内容評価を区別して保存する。"""
import json
import time
from pathlib import Path
import numpy as np
from campaign import ROOT,PRIOR,RESULT,digest,save
from revision_budget import RevisionBudget,REVISION
from acoustic_control import predict


def main():
    budget=RevisionBudget()
    with budget.job('audit','改訂版の完全性・制御不変性・残る評価を監査',3000000):
        protocol=json.loads((REVISION/'render-protocol.json').read_text());summaries={};evaluation_rows=[]
        for source,variants in [('render',protocol['models']),('refined',['direct_non_neural','distilled_non_neural'])]:
            summary={}
            for variant in variants:
                rows=[];responses=[]
                for row in protocol['rows']:
                    pair=[]
                    for condition in ['neutral','challenge']:
                        path=REVISION/source/row['id']/condition/(variant+'.json');rec=json.loads(path.read_text())
                        if digest(ROOT/rec['wav'])!=rec['wav_sha256']:raise ValueError('出力WAVの変更')
                        rows.append(rec);pair.append(rec)
                        evaluation_rows.append({'id':f'{source}/{row["id"]}/{condition}/{variant}',
                            'text':row['text'],'variant':variant,'condition':condition,'source':source,
                            'wav':rec['wav'],'wav_sha256':rec['wav_sha256'],'record_sha256':digest(path)})
                    a,b=pair
                    responses.append({'id':row['id'],
                        'f0_error':abs(b['measurement']['dio_f0_hz']/a['measurement']['dio_f0_hz']/(row['challenge']['requested_f0']/220)-1),
                        'duration_error':abs(b['measurement']['active_seconds']/a['measurement']['active_seconds']*row['challenge']['speed']-1)})
                targets=[r for r in rows if r.get('target')]
                ferr=[abs(r['measurement']['dio_f0_hz']/r['target']['f0_hz']-1) for r in targets]
                derr=[abs(r['measurement']['active_seconds']/r['target']['active_seconds']-1) for r in targets]
                summary[variant]={'n':len(rows),'E0_pass':sum(r['evaluation']['E0_pass'] for r in rows),
                    'saturated':sum(r['settings']['saturated'] for r in rows),
                    'response_n':len(responses),'f0_response_pass':sum(r['f0_error']<=.05 for r in responses),
                    'duration_response_pass':sum(r['duration_error']<=.10 for r in responses),'responses':responses,
                    'target_n':len(targets),'absolute_f0_pass':sum(e<=.05 for e in ferr),'absolute_duration_pass':sum(e<=.1 for e in derr),
                    'mean_absolute_f0_relative_error':float(np.mean(ferr)) if ferr else None,
                    'mean_absolute_duration_relative_error':float(np.mean(derr)) if derr else None}
            summaries[source]=summary
        runtime=json.loads((REVISION/'runtime-audit.json').read_text())
        if not runtime['passed']:raise ValueError('単独実行の検査が未達')
        contract=json.loads((REVISION/'runtime-audit/contract.json').read_text())
        for variant in contract['models']:
            for i,row in enumerate(contract['tests']):
                for mode in ['normal','isolated']:
                    wav=REVISION/'runtime-audit'/f'{variant}-{i}-{mode}.wav'
                    evaluation_rows.append({'id':f'runtime/{variant}/{i}/{mode}','text':row['text'],'variant':variant,
                        'condition':'runtime','source':'runtime','wav':str(wav.relative_to(ROOT)),'wav_sha256':digest(wav)})
        unique={}
        for row in evaluation_rows:
            h=row['wav_sha256']
            if h in unique:
                if row['text']!=unique[h]['text']:raise ValueError('同じ波形の参照文が不一致')
                unique[h]['aliases'].append(row['id'])
            else:unique[h]={**row,'aliases':[row['id']]}
        save(REVISION/'pending-content-evaluation.json',{'rows':list(unique.values()),'wav_count_before_deduplication':len(evaluation_rows),
            'unique_wav_count':len(unique),'engines':['Whisper base int8 beam5','ReazonSpeech k2 int8 greedy'],
            'requested_ai_calls':2*len(unique),'new_teacher_calls':0,'new_render_calls':0,'executed':False,
            'comparison':'同じ文・条件のnativeと直接/ニューラル/蒸留を両ASRで別々に比較。補正後も同じnativeを再利用',
            'runtime_scope':'未知2文は単独生成の内容診断で、native比較対照はこの2文にはない',
            'quality_scope':'工学修正後の既知8文を最終独立確認とは数えない。自然さの資格不足も残る'})
        checks=[]
        for variant in ['direct_non_neural','distilled_non_neural']:
            model=json.loads((REVISION/'models'/(variant+'.json')).read_text())
            for row in protocol['rows']:
                a=predict(model,row);b=predict(model,row,180.,.85)
                assert abs(b['unbounded_active_seconds']/a['unbounded_active_seconds']*.85-1)<1e-12
                assert abs(b['unbounded_f0_hz']/a['unbounded_f0_hz']/(180/220)-1)<1e-12
                checks.append({'model':variant,'id':row['id'],'target_equivariance':True})
        try:predict({'type':'ridge','quantity':'vtl-actuator'},protocol['rows'][0])
        except ValueError:pass
        else:raise AssertionError('異なる量のモデルを拒否しません')
        old_seals=[]
        for path in [PRIOR/'artifact-seal.json',PRIOR/'post-pilot/artifact-seal.json',RESULT/'artifact-seal.json',RESULT/'post-analysis/artifact-seal.json']:
            seal=json.loads(path.read_text());base=Path(seal['path_base'])
            if any(digest(base/p)!=h for p,h in seal['files'].items()):raise ValueError('先行封印の変更')
            old_seals.append({'path':str(path),'files_verified':len(seal['files'])})
        save(REVISION/'summary.json',{'comparisons':summaries,'runtime':runtime,'checks':checks,'wrong_quantity_rejected':True,
            'old_seals':old_seals,'content_evaluated':False,'perceptual_certified':False,'all_requirements_met':False,
            'selection_state':'研究用候補。直接版と蒸留版、補正前後を保持し、品質合格として採択しない'})
    events=budget.events();starts=[e for e in events if e['event']=='start'];ends={e['id'] for e in events if e['event']=='finish'}
    if any(e['id'] not in ends for e in starts):raise ValueError('未終了処理があります')
    counts={k:sum(e.get('count',1) for e in starts if e['kind']==k) for k in ['teacher','render','ai','train','setup','audit']}
    limits=budget.initialize();inv=budget.inventory();elapsed=time.time()-limits['started_epoch']
    within=all(counts[k]<=limits['limits'][k] for k in ['teacher','render','ai']) and inv['bytes']<limits['limits']['bytes'] and elapsed<limits['limits']['seconds']
    save(REVISION/'cost-audit.json',{'counts':counts,'limits':limits['limits'],'within_limits':within,'inventory':inv,
         'wall_seconds':elapsed,'pending':[],'failures':[e for e in events if e['event']=='finish' and e['status']!='completed'],
         'remaining_ai':limits['limits']['ai']-counts['ai'],'remaining_render':limits['limits']['render']-counts['render']})
    if not within:raise ValueError('上限を超過しています')
    print(json.dumps({'counts':counts,'pending_content_calls':len(unique)*2},ensure_ascii=False))


if __name__=='__main__':main()
