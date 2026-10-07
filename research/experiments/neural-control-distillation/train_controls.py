"""同じ開発資料から直接回帰・ニューラル制御・蒸留回帰を比較する。"""
import json
import time
import numpy as np
from budget import Budget, ROOT, RESULT, save, digest
from shared_control import features


def load_rows(split):
    rows = [r for r in json.loads((RESULT/'splits.json').read_text())['rows'] if r['split']==split]
    xs, ys, groups = [], [], []
    for row in rows:
        result = json.loads((RESULT/'fitted'/row['id']/'summary.json').read_text())
        control = result['fit']['best']['controls']
        x, bd, bf = features(row)
        y = np.stack([np.log(np.array(control['durations_seconds'])/bd),
                      np.log(np.array(control['f0_hz'])/bf)], axis=-1)
        xs.append(x); ys.append(y); groups.extend([row['id']]*len(x))
    return np.concatenate(xs), np.concatenate(ys), np.array(groups)


def group_mse(pred, target, groups):
    errors = np.mean((pred-target)**2, axis=1)
    return float(np.mean([errors[groups==g].mean() for g in sorted(set(groups))]))


def ridge(x, y, alpha):
    penalty = np.eye(x.shape[1])*alpha
    penalty[0,0] = 0
    return np.linalg.solve(x.T@x+penalty, x.T@y)


def main():
    import torch
    from torch import nn
    with Budget().job('train', '共有制御の直接学習と蒸留', 30_000_000):
        start = time.monotonic()
        torch.set_num_threads(2)
        torch.manual_seed(20261002)
        x, y, groups = load_rows('development')
        vx, vy, vg = load_rows('selection')
        xm, xs = x.mean(0), x.std(0)
        xs[xs<1e-6] = 1.
        xm[0], xs[0] = 0.,1.
        ym, ys = y.mean(0), y.std(0)
        ys[ys<1e-6] = 1.
        x, vx = (x-xm)/xs, (vx-xm)/xs
        y, vy = (y-ym)/ys, (vy-ym)/ys
        # 長い文が目的関数を支配しないよう、各文の合計重みを等しくする。
        weights = np.array([1/np.count_nonzero(groups==g) for g in groups])
        weights *= len(weights)/weights.sum()
        alphas = [.01,.1,1.,10.,100.]
        direct = []
        for alpha in alphas:
            coef = ridge(x*np.sqrt(weights[:,None]), y*np.sqrt(weights[:,None]), alpha)
            direct.append({'alpha':alpha,'score':group_mse(vx@coef,vy,vg),'coef':coef})
        net = nn.Sequential(nn.Linear(x.shape[1],32),nn.Tanh(),nn.Linear(32,32),nn.Tanh(),nn.Linear(32,2))
        optimizer = torch.optim.Adam(net.parameters(), lr=.003, weight_decay=.001)
        tx, ty = torch.tensor(x,dtype=torch.float32), torch.tensor(y,dtype=torch.float32)
        tw = torch.tensor(weights,dtype=torch.float32)
        tvx = torch.tensor(vx,dtype=torch.float32)
        checkpoints = []
        for epoch in range(1,2001):
            optimizer.zero_grad()
            error = ((net(tx)-ty)**2).mean(1)
            objective = (error*tw).mean()
            objective.backward()
            optimizer.step()
            if epoch in (200,500,1000,2000):
                net.eval()
                with torch.no_grad():
                    score = group_mse(net(tvx).numpy(),vy,vg)
                checkpoints.append({'epoch':epoch,'score':score,
                                    'state':{k:v.detach().clone() for k,v in net.state_dict().items()}})
                net.train()
        best_nn = min(checkpoints,key=lambda r:r['score'])
        net.load_state_dict(best_nn['state']);net.eval()
        with torch.no_grad():
            teacher_y = net(tx).numpy()
        students = []
        for alpha in alphas:
            coef = ridge(x*np.sqrt(weights[:,None]), teacher_y*np.sqrt(weights[:,None]), alpha)
            students.append({'alpha':alpha,'score':group_mse(vx@coef,vy,vg),'coef':coef})
        models = RESULT/'models'
        models.mkdir(exist_ok=True)
        normalization = {'x_mean':xm.tolist(),'x_scale':xs.tolist(),'y_mean':ym.tolist(),'y_scale':ys.tolist()}
        chosen = {}
        for name, candidates in [('direct_non_neural',direct),('distilled_non_neural',students)]:
            best = min(candidates,key=lambda r:r['score'])
            path = models/f'{name}.json'
            save(path, {'type':'ridge','name':name,**normalization,'coefficients':best['coef'].tolist(),
                        'alpha':best['alpha'],'feature_count':x.shape[1],
                        'input_contract':'文章由来の文脈のみ。発話ID・音声特徴なし'})
            chosen[name] = {'path':str(path.relative_to(ROOT)),'sha256':digest(path),
                            'alpha':best['alpha'],'selection_score':best['score']}
        nn_path = models/'neural_control.pt'
        torch.save(net.state_dict(),nn_path)
        save(models/'neural_control.json', {**normalization,'input_size':x.shape[1],'hidden_size':32,
             'state_dict':str(nn_path.relative_to(ROOT)),'research_only':True,'seed':20261002})
        chosen['neural_control'] = {'path':str(nn_path.relative_to(ROOT)),'sha256':digest(nn_path),
                                  'epoch':best_nn['epoch'],'selection_score':best_nn['score']}
        save(RESULT/'model-selection.json', {
            'chosen':chosen,'frozen_before_audit':True,'audit_opened':False,
            'development_phone_rows':len(x),'development_utterances':len(set(groups)),
            'selection_phone_rows':len(vx),'selection_utterances':len(set(vg)),
            'feature_count':x.shape[1],'seconds':time.monotonic()-start,
            'candidates':{'direct':[{'alpha':r['alpha'],'score':r['score']} for r in direct],
                          'neural':[{'epoch':r['epoch'],'score':r['score']} for r in checkpoints],
                          'student':[{'alpha':r['alpha'],'score':r['score']} for r in students]},
            'limitations':'制御誤差による候補選択のみ。実音比較と内容保護を経て採択を決める',
            'source_hashes':{p.name:digest(p) for p in ROOT.glob('*.py')}})
        print(json.dumps({'chosen':chosen,'seconds':time.monotonic()-start},ensure_ascii=False))


if __name__ == '__main__':
    main()
