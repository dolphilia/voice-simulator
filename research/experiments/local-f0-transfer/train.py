"""同じ16特徴・独立発話重みで直接回帰、ニューラル、蒸留を学習する。"""
import numpy as np
from campaign import LocalBudget, ROOT, RESULT, read, save, digest
from local_control import FEATURES


def data(split):
    paths = sorted((RESULT/'training-inputs'/split).glob('*.json'))
    records = [read(p) for p in paths if read(p)['status'] == 'available']
    x, y, groups = [], [], []
    for i, record in enumerate(records):
        for phone in record['phones']:
            x.append(phone['x'])
            y.append(phone['target_half_tone'])
            groups.append(i)
    return np.array(x), np.array(y), np.array(groups), records


def centered(values, groups):
    result = np.array(values, copy=True)
    for g in set(groups):
        mask = groups == g
        result[mask] -= result[mask].mean(axis=0)
    return result


def bounded(values, groups):
    result = np.clip(values, -3, 3)
    result = centered(result, groups)
    for g in set(groups):
        mask = groups == g
        result[mask] *= min(1., 3/max(1e-12, np.max(abs(result[mask]))))
    return result


def weighted_mse(values, target, groups):
    return float(np.mean([np.mean((values[groups == g]-target[groups == g])**2) for g in set(groups)]))


def main():
    import torch
    from torch import nn
    b = LocalBudget()
    protocol = read(RESULT/'protocol.json')
    for name, sha in protocol['source_hashes'].items():
        assert digest(ROOT/name) == sha
    x, y, groups, rows = data('development')
    vx, vy, vgroups, vrows = data('selection')
    mean, scale = x.mean(0), x.std(0)
    scale[scale < 1e-6] = 1.
    mean[0], scale[0] = 0., 1.
    z, vz = (x-mean)/scale, (vx-mean)/scale
    cz = centered(z, groups)
    weight = np.array([1./sum(groups == g) for g in groups])
    normal = {'x_mean': mean.tolist(), 'x_scale': scale.tolist(), 'features': FEATURES}
    with b.job('setup', '3fitの資料・特徴・正則化・中心化を事前固定', 1_000_000):
        save(RESULT/'training-contract.json', {'protocol_sha256': digest(RESULT/'protocol.json'),
            'input_files': {str(p.relative_to(ROOT)): digest(p) for p in (RESULT/'training-inputs').rglob('*.json')},
            'training_utterances': len(rows), 'training_phone_intervals': len(y),
            'selection_utterances': len(vrows), 'selection_phone_intervals': len(vy),
            'feature_rank_centered': int(np.linalg.matrix_rank(cz)), 'features': FEATURES,
            'planned_fits': 3, 'steps': 500, 'ridge_lambda': 10., 'seed': 20261003,
            'source_sha256': digest(ROOT/'train.py'), 'selection_used_to_tune': False,
            'target_kind': '教師DIOとHMM状態平均の中心化形状差。手動境界・波形同士の誤差ではない。',
            'independent_samples': '発話21。音素区間を独立文数へ加算しない。',
            'runtime_vs_training_support': '訓練は教師F0の採用区間のみで中心化。実行時は全対象有声音素で中心化。支持域差を保持する。'})
    models = RESULT/'models'
    with b.job('train', '局所16係数の直接回帰fit', 1_000_000):
        direct = np.linalg.solve(cz.T@(weight[:, None]*cz)+10.*np.eye(16), cz.T@(weight*y))
        save(models/'direct_non_neural.json', {**normal, 'type': 'local-ridge', 'coefficients': direct.tolist(),
            'lambda': 10., 'training_contract_sha256': digest(RESULT/'training-contract.json'), 'runtime_neural': False})
    torch.set_num_threads(2)
    torch.manual_seed(20261003)
    net = nn.Sequential(nn.Linear(16, 16), nn.Tanh(), nn.Linear(16, 16), nn.Tanh(), nn.Linear(16, 1))
    tx = torch.tensor(z, dtype=torch.float32)
    ty = torch.tensor(y, dtype=torch.float32)
    tw = torch.tensor(weight/len(rows), dtype=torch.float32)
    masks = [torch.tensor(groups == g) for g in sorted(set(groups))]
    losses = []
    with b.job('train', '局所F0の研究用ニューラルfit', 1_000_000):
        optimizer = torch.optim.Adam(net.parameters(), lr=.005, weight_decay=.001)
        for step in range(500):
            optimizer.zero_grad()
            prediction = net(tx).flatten()
            result = prediction.clone()
            for mask in masks:
                result[mask] = prediction[mask]-prediction[mask].mean()
            loss = torch.sum(tw*(result-ty)**2)
            loss.backward()
            optimizer.step()
            if step in (0, 99, 249, 499):
                losses.append({'step': step+1, 'weighted_loss': float(loss.detach())})
        net.eval()
        torch.save(net.state_dict(), models/'neural.pt')
        save(models/'neural.json', {**normal, 'type': 'local-neural', 'width': 16, 'layers': 2,
            'weights_sha256': digest(models/'neural.pt'), 'research_only': True, 'training_steps': 500,
            'training_contract_sha256': digest(RESULT/'training-contract.json')})
    with torch.no_grad():
        neural_targets = centered(net(tx).flatten().numpy(), groups)
    with b.job('train', '同じ16係数の蒸留回帰fit', 1_000_000):
        student = np.linalg.solve(cz.T@(weight[:, None]*cz)+10.*np.eye(16), cz.T@(weight*neural_targets))
        save(models/'distilled_non_neural.json', {**normal, 'type': 'local-ridge', 'coefficients': student.tolist(),
            'lambda': 10., 'teacher_model_sha256': digest(models/'neural.pt'),
            'training_contract_sha256': digest(RESULT/'training-contract.json'), 'runtime_neural': False})
    with b.job('audit', '同一選別12文で局所形状の適合損失を記録', 1_000_000):
        with torch.no_grad():
            nv = net(torch.tensor(vz, dtype=torch.float32)).flatten().numpy()
        metrics = {}
        for name, prediction in [('native', np.zeros(len(vy))), ('direct_non_neural', vz@direct),
                                 ('neural', nv), ('distilled_non_neural', vz@student)]:
            metrics[name] = {'selection_weighted_mse_half_tone': weighted_mse(bounded(prediction, vgroups), vy, vgroups),
                             'raw_predictions_over_3': int(np.sum(abs(prediction) > 3))}
        save(RESULT/'model-comparison.json', {'selection_metrics': metrics, 'training_losses': losses,
            'model_hashes': {p.name: digest(p) for p in models.iterdir()},
            'all_models_frozen_before_unknown_render': True, 'quality_certified': False,
            'no_model_selection_from_asr': True, 'source_sha256': digest(ROOT/'train.py')})
    print(metrics)


if __name__ == '__main__':
    main()
