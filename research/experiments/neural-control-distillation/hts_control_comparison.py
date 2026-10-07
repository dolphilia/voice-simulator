"""追加HMM分岐に直接学習・ニューラル制御の固定対照を加える。"""
import json
import numpy as np
from scipy.io import wavfile
from budget import Budget,ROOT,RESULT,save,digest
from hts_transfer import render_hts
from fit_controls import measure,loss
from acoustics import evaluate
from shared_control import features,decode,predict


def main():
    import pyopenjtalk
    import torch
    from torch import nn
    budget=Budget()
    out=RESULT/'hts-transfer'
    with budget.job('setup','HMM分岐の直接学習・ニューラル対照を固定',1_000_000):
        selection=json.loads((RESULT/'model-selection.json').read_text())
        for model in selection['chosen'].values():
            if digest(ROOT/model['path'])!=model['sha256']:raise ValueError('凍結モデルの不一致')
        save(out/'control-comparison-protocol.json',{'models':selection['chosen'],
            'posthoc_diagnostic':True,'reason':'蒸留モデルだけの結果をニューラル経由の優位性と誤認しないため',
            'retrained':False,'tuned_on_new_four':False,'render_calls':8,'ai_calls':16,
            'comparison':'同じ4文・同じHMM・同じ全体量への写像。音素別制御の移植ではない'})
    config=json.loads((RESULT/'models/neural_control.json').read_text())
    net=nn.Sequential(nn.Linear(config['input_size'],32),nn.Tanh(),nn.Linear(32,32),nn.Tanh(),nn.Linear(32,2))
    net.load_state_dict(torch.load(ROOT/config['state_dict'],map_location='cpu',weights_only=True))
    net.eval();torch.set_num_threads(2)
    direct=json.loads((RESULT/'models/direct_non_neural.json').read_text())
    voice=__import__('pathlib').Path(pyopenjtalk.__file__).parent/'htsvoice/mei_normal.htsvoice'
    for row in json.loads((out/'protocol.json').read_text())['rows']:
        base=json.loads((out/row['id']/'baseline.json').read_text())['measurement']
        target=json.loads((out/row['id']/'teacher.json').read_text())['measurement']
        for name in ('direct_non_neural','neural_control'):
            if name=='direct_non_neural':d,f,bounds=predict(direct,row)
            else:
                x,_,_=features(row)
                x=(x-np.array(config['x_mean']))/np.array(config['x_scale'])
                with torch.no_grad():y=net(torch.tensor(x,dtype=torch.float32)).numpy()
                d,f,bounds=decode(row,y*np.array(config['y_scale'])+np.array(config['y_mean']))
            desired={'active_seconds':float(sum(d)),'f0_hz':float(np.exp(np.sum(d*np.log(f))/sum(d)))}
            speed=float(base['active_seconds']/desired['active_seconds'])
            half_tone=float(12*np.log2(desired['f0_hz']/base['f0_hz']))
            settings={'speed':float(np.clip(speed,.6,1.6)),'half_tone':float(np.clip(half_tone,-6,6)),
                      'unbounded_speed':speed,'unbounded_half_tone':half_tone,'desired':desired,'phone_bounds':bounds}
            path=out/row['id']/f'{name}.json'
            with budget.job('render',f'HMM追加対照/{name}/{row["id"]}',3_000_000):
                audio=render_hts(row,voice,settings['speed'],settings['half_tone'])
                measured=measure(audio)
                wavfile.write(path.with_suffix('.wav'),24000,audio.astype(np.float32))
                save(path,{'id':row['id'],'text':row['text'],'settings':settings,'measurement':measured,
                    'objective':loss(measured,target),'evaluation':evaluate(audio,{},24000),
                    'wav':str(path.with_suffix('.wav').relative_to(ROOT)),'sha256':digest(path.with_suffix('.wav')),
                    'runtime_neural':name=='neural_control','reference_used_by_controller':False})
                print(row['id'],name,loss(measured,target),flush=True)


if __name__=='__main__':main()
