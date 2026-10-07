"""受理した実波形制御を同じ全有声音素集合の共有関数へ移す。"""
import numpy as np
from campaign import LocalBudget, ROOT, RESULT, REPO, LRES, read, save, digest
from local_control import FEATURES, ELIGIBLE, describe, deltas
from centered_projection import project


def centered(values,groups):
    output=np.array(values,copy=True)
    for g in sorted(set(groups)):output[groups==g]-=output[groups==g].mean(axis=0)
    return output


def projected(values,groups):
    output=np.array(values,copy=True)
    for g in sorted(set(groups)):output[groups==g]=project(output[groups==g])
    return output


def weighted_mse(values,target,groups):
    return float(np.mean([np.mean((values[groups==g]-target[groups==g])**2) for g in sorted(set(groups))]))


def main():
    manifest=read(RESULT/'target-manifest.json');assert manifest['fit_supported'],'最低12文の目標資格が未達のため共有fitを禁止'
    import torch
    from torch import nn
    b=LocalBudget()
    assert not (RESULT/'asr').exists()
    for n,sha in read(RESULT/'shared-stage-contract.json')['source_hashes'].items():assert digest(ROOT/n)==sha
    p=read(RESULT/'protocol.json');x=[];y=[];groups=[];used=[]
    for item in manifest['rows']:
        if not item['qualification']['qualified']:continue
        row=next(r for r in p['training_rows'] if r['id']==item['id']);source=read(REPO/row['source_training_input'])
        best=read(RESULT/'searches'/(row['id']+'.json'))['wavefit'];snapshot=source['snapshot']
        allphones=[d for d in describe(row) if d['phone'] in ELIGIBLE and any(snapshot['msd'][j]>.5 for j in range(d['label_index']*5,(d['label_index']+1)*5))]
        target=best['phone_residuals'];assert [d['label_index'] for d in allphones]==[d['label_index'] for d in target]
        correction,regenerated=deltas(row,snapshot,lambda features:np.asarray(features)[:,[10,11,12,13]]@np.asarray(best['coefficients']))
        assert regenerated==target
        assert abs(sum(d['half_tone'] for d in target))<1e-10
        g=len(used)
        for d,t in zip(allphones,target):x.append(d['x']);y.append(t['half_tone']);groups.append(g)
        used.append({'id':row['id'],'text':row['text'],'length':row['length'],'target_wav_sha256':best['wav_sha256'],
            'target_attempt':best['attempt'],'all_eligible_labels':[d['label_index'] for d in allphones],
            'target_half_tone':[d['half_tone'] for d in target],'target_coefficients':best['coefficients']})
    assert len(used)>=12 and {r['length'] for r in used}=={'short','long'}
    x,y,groups=np.asarray(x),np.asarray(y),np.asarray(groups);mean,scale=x.mean(0),x.std(0)
    scale[scale<1e-6]=1.;mean[0],scale[0]=0.,1.;z=(x-mean)/scale;cz=centered(z,groups)
    weight=np.array([1./sum(groups==g) for g in groups]);normal={'x_mean':mean.tolist(),'x_scale':scale.tolist(),'features':FEATURES}
    with b.job('setup','実波形目標・全有声音素・3fit設定を固定',2000000):
        save(RESULT/'training-contract.json',{'protocol_sha256':digest(RESULT/'protocol.json'),'target_manifest_sha256':digest(RESULT/'target-manifest.json'),
            'training_utterances':len(used),'training_phone_intervals':len(y),'used':used,'features':FEATURES,
            'feature_rank_centered':int(np.linalg.matrix_rank(cz)),'planned_fits':3,'steps':500,'ridge_lambda':10.,'seed':20261003,
            'target_kind':'実波形で受理した制御。測定支持域の外も含む実行時と同一の全対象有声音素残差。',
            'selection_used_to_tune':False,'training_and_runtime_support_identical':True,'source_sha256':digest(ROOT/'train.py')})
    models=RESULT/'models'
    with b.job('train','実波形目標の直接16係数回帰fit',1000000):
        direct=np.linalg.solve(cz.T@(weight[:,None]*cz)+10.*np.eye(16),cz.T@(weight*y))
        save(models/'direct_non_neural.json',{**normal,'type':'local-ridge','coefficients':direct.tolist(),'lambda':10.,
            'training_contract_sha256':digest(RESULT/'training-contract.json'),'runtime_neural':False})
    torch.set_num_threads(2);torch.manual_seed(20261003)
    net=nn.Sequential(nn.Linear(16,16),nn.Tanh(),nn.Linear(16,16),nn.Tanh(),nn.Linear(16,1))
    tx=torch.tensor(z,dtype=torch.float32);ty=torch.tensor(y,dtype=torch.float32);tw=torch.tensor(weight/len(used),dtype=torch.float32)
    masks=[torch.tensor(groups==g) for g in sorted(set(groups))]
    def projection(prediction):
        output=prediction.clone()
        for mask in masks:
            values=prediction[mask]-prediction[mask].mean()
            ratio=torch.clamp(3./torch.clamp(torch.max(torch.abs(values)),min=1e-12),max=1.)
            output[mask]=values*ratio
        return output
    losses=[]
    with b.job('train','実波形目標の研究NN固定500step fit',2000000):
        optimizer=torch.optim.Adam(net.parameters(),lr=.005,weight_decay=.001)
        for step in range(500):
            optimizer.zero_grad();prediction=projection(net(tx).flatten());loss=torch.sum(tw*(prediction-ty)**2)
            loss.backward();optimizer.step()
            if step in (0,99,249,499):losses.append({'step':step+1,'weighted_projected_loss':float(loss.detach())})
        net.eval();torch.save(net.state_dict(),models/'neural.pt')
        save(models/'neural.json',{**normal,'type':'local-neural','width':16,'layers':2,'weights_sha256':digest(models/'neural.pt'),
            'research_only':True,'training_steps':500,'training_contract_sha256':digest(RESULT/'training-contract.json')})
    with torch.no_grad():neural_raw=net(tx).flatten().numpy();neural_targets=projected(neural_raw,groups)
    with b.job('train','同じ16係数へ研究NNを蒸留fit',1000000):
        student=np.linalg.solve(cz.T@(weight[:,None]*cz)+10.*np.eye(16),cz.T@(weight*neural_targets))
        save(models/'distilled_non_neural.json',{**normal,'type':'local-ridge','coefficients':student.tolist(),'lambda':10.,
            'teacher_model_sha256':digest(models/'neural.pt'),'training_contract_sha256':digest(RESULT/'training-contract.json'),'runtime_neural':False})
    with b.job('audit','共有モデル固定と訓練損失・旧状態目標版との差',1000000):
        metrics={name:weighted_mse(projected(values,groups),y,groups) for name,values in
            [('native',np.zeros(len(y))),('direct_non_neural',z@direct),('neural',neural_raw),('distilled_non_neural',z@student)]}
        old={n:{'path':str((LRES/'models'/n).relative_to(REPO)),'sha256':digest(LRES/'models'/n)} for n in ('direct_non_neural.json','neural.json','neural.pt','distilled_non_neural.json')}
        save(RESULT/'model-comparison.json',{'training_mse':metrics,'training_losses':losses,'old_state_target_models':old,
            'model_hashes':{path.name:digest(path) for path in models.iterdir()},'all_models_frozen_before_diagnostic_render':True,
            'no_model_selection_from_asr':True,'quality_certified':False})
    print({'training_utterances':len(used),'phone_intervals':len(y),'training_mse':metrics},flush=True)

if __name__=='__main__':main()
