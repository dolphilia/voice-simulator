"""凍結した共有制御を同じ実レンダラーで比較する。"""
import json
import sys
import time
import numpy as np
from budget import Budget, ROOT, RESULT, save, digest
from shared_control import features, decode, predict
from fit_controls import trial
sys.path.insert(0, str(ROOT.parent/'autonomous-speech-synthesis/src'))
from autonomous_speech_synthesis.backends import VTL


def main():
    import torch
    from torch import nn
    selection = json.loads((RESULT/'model-selection.json').read_text())
    for model in selection['chosen'].values():
        if digest(ROOT/model['path']) != model['sha256']:
            raise ValueError('凍結したモデルが変わりました')
    config = json.loads((RESULT/'models/neural_control.json').read_text())
    net = nn.Sequential(nn.Linear(config['input_size'],32),nn.Tanh(),nn.Linear(32,32),nn.Tanh(),nn.Linear(32,2))
    net.load_state_dict(torch.load(ROOT/config['state_dict'],map_location='cpu',weights_only=True))
    torch.set_num_threads(2)
    net.eval()
    models = {name:json.loads((RESULT/'models'/f'{name}.json').read_text())
              for name in ('direct_non_neural','distilled_non_neural')}
    rows = json.loads((RESULT/'splits.json').read_text())['rows']
    vtl, budget = VTL(), Budget()
    try:
        for row in rows:
            fitted = json.loads((RESULT/'fitted'/row['id']/'summary.json').read_text())
            for name in ('direct_non_neural','neural_control','distilled_non_neural'):
                path = RESULT/'comparisons'/name/row['id']
                if path.with_suffix('.json').exists():
                    continue
                start = time.monotonic()
                if name == 'neural_control':
                    x, _, _ = features(row)
                    x = (x-np.array(config['x_mean']))/np.array(config['x_scale'])
                    with torch.no_grad():
                        y = net(torch.tensor(x,dtype=torch.float32)).numpy()
                    y = y*np.array(config['y_scale'])+np.array(config['y_mean'])
                    d, f, bounds = decode(row,y)
                else:
                    d, f, bounds = predict(models[name],row)
                control_seconds = time.monotonic()-start
                record = trial(vtl,budget,f'{name}/{row["id"]}',row['phonemes'],d,f,
                               fitted['target'],path)
                save(path.with_suffix('.control.json'), {'id':row['id'],'split':row['split'],
                     'model':name,'prediction_seconds':control_seconds,'bounds':bounds,
                     'runtime_neural':name=='neural_control', 'input_includes_reference_audio':False})
                print(json.dumps({'id':row['id'],'model':name,'objective':record['objective'],
                                  'bounds':bounds},ensure_ascii=False),flush=True)
    finally:
        vtl.close()


if __name__ == '__main__':
    main()
