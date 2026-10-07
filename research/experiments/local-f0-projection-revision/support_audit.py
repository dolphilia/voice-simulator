"""保存済み区間・特徴・実波形だけで支持域と制御の制約を監査する。"""
import numpy as np
from campaign import LocalBudget, ROOT, RESULT, LRES, read, save, digest
from local_control import describe, ELIGIBLE, FEATURES

def main():
    with LocalBudget().job('audit','保存済み区間・特徴支持域・実制御の原因点検',1000000):
        records = [read(p) for p in sorted((LRES/'training-inputs').rglob('*.json'))]
        training = [r for r in records if r['split'] == 'development' and r['status'] == 'available']
        selection = [r for r in records if r['split'] == 'selection' and r['status'] == 'available']
        model = read(RESULT/'models/direct_non_neural.json')
        mean, scale = np.array(model['x_mean']), np.array(model['x_scale'])
        x = np.array([p['x'] for r in training for p in r['phones']]); z=(x-mean)/scale
        low, high = x.min(0), x.max(0)
        centered = np.concatenate([np.array([p['x'] for p in r['phones']])-np.mean([p['x'] for p in r['phones']],axis=0) for r in training])
        _, s, vt = np.linalg.svd(centered/scale, full_matrices=False)
        rank = int(np.sum(s > s[0]*1e-10)); basis=vt[:rank]
        support = []
        for r in training+selection:
            eligible = [d for d in describe(r['row']) if d['phone'] in ELIGIBLE and any(r['snapshot']['msd'][j]>.5 for j in range(d['label_index']*5,(d['label_index']+1)*5))]
            targets = {p['label_index'] for p in r['phones']}
            support.append({'id':r['id'],'split':r['split'],'eligible_runtime_phones':len(eligible),
                'teacher_target_phones':len(targets),'runtime_phones_without_teacher_target':sum(d['label_index'] not in targets for d in eligible)})
        manifest = read(RESULT/'render-manifest.json'); new = []
        for row in read(RESULT/'protocol.json')['rows']:
            direct = next(r for r in manifest['rows'] if r['id'] == row['id']+'/neutral/direct_non_neural')
            indices = {p['label_index'] for p in direct['phone_residuals']}
            d = [p for p in describe(row) if p['label_index'] in indices]
            xx=np.array([p['x'] for p in d]); zz=(xx-mean)/scale
            distance=np.sqrt(np.sum((zz[:,None,:]-z[None,:,:])**2,axis=2)).min(axis=1)
            centered_new=(xx-xx.mean(axis=0))/scale
            unsupported=centered_new-(centered_new@basis.T)@basis
            outside=(xx<low-1e-12)|(xx>high+1e-12)
            new.append({'id':row['id'],'text':row['text'],'eligible_phones':len(d),
                'outside_training_coordinate_range_phones':int(outside.any(axis=1).sum()),
                'outside_training_coordinates':[FEATURES[i] for i in np.flatnonzero(outside.any(axis=0))],
                'nearest_training_feature_distance_median':float(np.median(distance)),
                'nearest_training_feature_distance_max':float(distance.max()),
                'centered_training_nullspace_residual_max':float(np.linalg.norm(unsupported,axis=1).max())})
        targets=np.array([p['target_half_tone'] for r in training for p in r['phones']])
        coeff=np.array(model['coefficients']); student=np.array(read(RESULT/'models/distilled_non_neural.json')['coefficients'])
        save(RESULT/'support-audit.json',{'source_training_contract_sha256':digest(LRES/'training-contract.json'),
            'source_training_inputs_sha256':{str(p.relative_to(LRES)):digest(p) for p in sorted((LRES/'training-inputs').rglob('*.json'))},
            'new_wave_calls':0,'new_ai_calls':0,'new_fit_calls':0,'models_changed':False,
            'training_texts':len(training),'selection_texts':len(selection),'training_phones':len(x),
            'centered_feature_rank':rank,'feature_count':16,'singular_values':s.tolist(),
            'support_by_saved_utterance':support,'new_text_support':new,
            'target_half_tone_quantiles':np.quantile(targets,[0,.1,.5,.9,1]).tolist(),
            'training_target_abs_over_3':int((abs(targets)>3).sum()),
            'direct_student_coefficient_l2':float(np.linalg.norm(student-coeff)),
            'limitations':['教師区間は内部時間予測。人手境界の正解ではない。','支持域距離は発音・自然さの品質指標ではない。','区間の時間・スペクトル・音源は今回変更していない。'],
            'quality_certified':False})
    print('支持域・教師区間監査を保存',flush=True)

if __name__ == '__main__': main()
