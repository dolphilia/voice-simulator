"""科学的契約を保持し、未保存の比較だけを外部保存で続行する。"""
from paths import *
import sys
from storage_budget import StorageBudget
import run as original

def main():
    b=StorageBudget()
    p=read(HERE/'protocol.json')
    ec=read(HERE/'execution-contract.json')
    models=read(HERE/'model-comparison.json')
    for n,h in p['dependencies'].items():assert digest(REPO/n)==h
    for n,h in ec['source_hashes'].items():assert digest(HERE/n)==h
    for n,h in ec['external_generation_sources'].items():assert digest(REPO/n)==h
    for n,h in models['model_hashes'].items():assert digest(HERE/'models'/n)==h
    assert ec['gain_contract_sha256']==digest(HERE/'gain-contract.json')
    complete=[]
    for path in (HERE/'render').rglob('*.json'):
        if path.name.endswith('.render.json'):continue
        r=read(path)
        assert r['status']=='completed'
        assert digest(REPO/r['wav'])==r['wav_sha256']
        assert digest(REPO/r['parameters'])==r['parameters_sha256']
        complete.append(path)
    assert len(complete)==847
    for path in (HERE/'render').rglob('*.wav'):
        assert path.with_suffix('.json').exists(), '未完了波形を自動で上書きしません'
    b.reconcile()
    with b.job(NAME,'setup','保存経路のみ更新して847件をhash照合し再開',reserve_bytes=100000) as j:
        b.save(HERE/'generation-storage-amendment-01.json',
               dict(previous_execution_contract_sha256=digest(HERE/'execution-contract.json'),
                    storage_amendment_id=b.storage['amendment_id'],
                    wrapper_sha256=digest(Path(__file__)),
                    storage_sources={n:digest(ROOT/n) for n in ['storage_budget.py','storage_guard.py']},
                    completed_records=847,remaining_records=49,failed_attempt_retained=True,
                    scientific_sources_models_gain_inputs_gates_unchanged=True,
                    old_sealed_files_not_moved=True,quality_certified=False),j)
    predictors={v:(lambda x,m=read(HERE/'models'/(v.split('_')[0]+'.json')):original.predict(m,x))
                for v in p['variants'] if v.startswith(('direct_','student_'))}
    nn=original.predictor()
    predictors.update({v:nn for v in p['variants'] if v.startswith('neural_')})
    records=[]
    for row in p['training_rows']:
        for v in p['training_variants']:
            records.append(original.run_one(b,row,'neutral',v,'training',predictors))
    for row in p['rows']:
        for c in row['requests']:
            for v in p['variants']:
                records.append(original.run_one(b,row,c,v,'diagnostic',predictors))
        print('保存済み照合/未実施再開',row['id'],flush=True)
    assert len(records)==896
    b.save(HERE/'render-manifest.json',
           dict(rows=[dict(id=r['mode']+'/'+r['id'],
                          record=str((HERE/'render'/r['mode']/(r['id']+'.json')).relative_to(REPO)),
                          wav=r['wav'],wav_sha256=r['wav_sha256']) for r in records],
                search_completed_before_ASR=True,training_records=560,diagnostic_records=336,
                reused_training_renders=320,new_training_renders=240,new_diagnostic_renders=336,
                planned_ASR_records=1792,training_ASR_not_independent_quality=True,
                all_models_fixed_before_audio=True,quality_certified=False))
    print(dict(external_files_hashed=b.audit_data_hashes(),reconcile=b.reconcile()),flush=True)

if __name__=='__main__':main()
