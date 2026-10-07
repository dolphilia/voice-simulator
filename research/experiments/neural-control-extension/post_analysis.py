"""封印後に保存済みデータだけで回帰の外挿を点検する。生成・AI推論はしない。"""
import json
import os
import sys
import numpy as np
from campaign import ExtensionBudget, ROOT, PILOT, PRIOR, RESULT, digest, save
POST = RESULT/'post-analysis'
sys.path.insert(0, str(PRIOR/'hts-bundle-v2'))
from shared_control import features, predict
from extract_controls import align


class PostBudget(ExtensionBudget):
    def events(self):
        path = POST/'ledger.jsonl'
        return super().events()+([json.loads(s) for s in path.read_text().splitlines()] if path.exists() else [])

    def append(self, row):
        POST.mkdir(parents=True, exist_ok=True)
        with (POST/'ledger.jsonl').open('a') as f:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
            f.flush()
            os.fsync(f.fileno())

    def reserve(self, kind, *args, **kwargs):
        if kind != 'audit':
            raise ValueError('この追記は保存データの監査だけを許可します')
        seal = json.loads((RESULT/'artifact-seal.json').read_text())
        name = str((RESULT/'ledger.jsonl').relative_to(ROOT.parents[2]))
        if digest(RESULT/'ledger.jsonl') != seal['files'][name]:
            raise ValueError('封印済み台帳が変更されています')
        return super().reserve(kind, *args, **kwargs)


GROUPS = {'bias': [0], 'phone': list(range(1,38)), 'neighbors': list(range(38,52)),
          'position': [52,53,54,55], 'length': [56], 'mora_accent_phrase': list(range(57,62)),
          'requested_controls': [62,63], 'phone_position_interaction': list(range(64,101))}


def model_analysis(model, row):
    x, bd, _ = features(row)
    z = (x-np.array(model['x_mean']))/np.array(model['x_scale'])
    coefficients = np.array(model['coefficients'])
    yscale = np.array(model['y_scale'])
    ymean = np.array(model['y_mean'])
    w = bd/sum(bd)
    contribution = np.sum(w[:,None]*z, axis=0)[:,None]*coefficients*yscale
    raw_y = z@coefficients*yscale+ymean
    weighted_y = np.sum(w[:,None]*raw_y, axis=0)
    if not np.allclose(contribution.sum(axis=0)+ymean, weighted_y, atol=1e-12, rtol=0):
        raise ValueError('線形寄与の再構成が不一致')
    d, f, bounds = predict(model, row)
    return {'predicted_seconds': float(sum(d)), 'baseline_seconds': float(sum(bd)),
            'log_total_duration_ratio': float(np.log(sum(d)/sum(bd))),
            'weighted_log_correction': weighted_y.tolist(),
            'feature_contributions': {key: contribution[index].sum(axis=0).tolist() for key, index in GROUPS.items()},
            'duration_jensen_and_bound_residual': float(np.log(sum(d)/sum(bd))-weighted_y[0]),
            'phone_bounds': bounds, 'phone_count': len(d)}


def main():
    budget = PostBudget()
    with budget.job('audit', '既存教師の音素対応と回帰の外挿寄与を分解', 3000000):
        training = [r for r in json.loads((PRIOR/'splits.json').read_text())['rows'] if r['split'] == 'development']
        unknown = json.loads((RESULT/'protocol.json').read_text())['rows']
        x = np.concatenate([features(r)[0] for r in training])
        models = {v: json.loads((PRIOR/'hts-bundle-v2'/(v+'.json')).read_text()) for v in ['direct_non_neural','distilled_non_neural']}
        records = []
        for scope, rows in [('development',training), ('extension',unknown)]:
            for row in rows:
                p = (PRIOR/'teacher'/f"{row['id']}.json") if scope == 'development' else (RESULT/'teacher/jf_alpha'/f"{row['id']}.json")
                teacher = json.loads(p.read_text())
                base = PILOT if scope == 'development' else ROOT
                if digest(base/teacher['wav']) != teacher['wav_sha256']:
                    raise ValueError('教師波形のハッシュ不一致')
                record = {'id': row['id'], 'scope': scope, 'text': row['text'],
                          'models': {v: model_analysis(m,row) for v,m in models.items()}}
                try:
                    intervals, gaps = align(row, teacher)
                    durations = np.array([r['end']-r['start'] for r in intervals])
                    if not np.isfinite(durations).all() or not (durations>0).all():
                        raise ValueError('対応付けの継続長が非正です')
                    record['teacher_alignment'] = {'status': 'available', 'internal_seconds': float(sum(durations)),
                        'phonemes_exact_match': True, 'gap_count': len(gaps), 'is_manual_ground_truth': False}
                    for v in models:
                        record['models'][v]['predicted_to_teacher_internal_duration_ratio'] = record['models'][v]['predicted_seconds']/float(sum(durations))
                except ValueError as e:
                    record['teacher_alignment'] = {'status': 'unavailable', 'error': str(e)}
                records.append(record)
        summary = {}
        for v in models:
            development = [r['models'][v] for r in records if r['scope']=='development']
            extension = [r['models'][v] for r in records if r['scope']=='extension']
            delta = {key: (np.mean([r['feature_contributions'][key] for r in extension],axis=0)-np.mean([r['feature_contributions'][key] for r in development],axis=0)).tolist() for key in GROUPS}
            summary[v] = {'feature_contribution_mean_delta_extension_minus_development': delta,
                'total_log_duration_mean_delta': float(np.mean([r['log_total_duration_ratio'] for r in extension])-np.mean([r['log_total_duration_ratio'] for r in development])),
                'duration_ratios': {scope: [r['models'][v]['predicted_to_teacher_internal_duration_ratio'] for r in records if r['scope']==scope and r['teacher_alignment']['status']=='available'] for scope in ['development','extension']}}
        fit_scales = []
        for row in training:
            fit = json.loads((PRIOR/'fitted'/row['id']/'summary.json').read_text())
            fit_scales.append({'id':row['id'], 'duration':fit['fit']['best']['scales'][0], 'f0':fit['fit']['best']['scales'][1]})
        save(POST/'regression-audit.json', {'records':records, 'summary':summary, 'training_feature_matrix':{'rows':len(x),'columns':x.shape[1], 'rank':int(np.linalg.matrix_rank(x)), 'min':x.min(0).tolist(),'max':x.max(0).tolist()},
            'renderer_fit_scales':fit_scales,'new_generation':0,'new_ai_inference':0,'new_training':0,
            'scope':'凍結結果の原因診断。教師内部時間は人手境界ではなく、VTL適合済み時間と同一ではない。合否やモデルを改訂しない'})
        print(json.dumps({'summary':summary,'alignment_available':{scope:sum(r['scope']==scope and r['teacher_alignment']['status']=='available' for r in records) for scope in ['development','extension']}},ensure_ascii=False))


if __name__ == '__main__':
    main()
