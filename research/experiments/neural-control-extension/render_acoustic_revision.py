"""未知8文で改訂制御の音響応答を比較する。内容・自然さは未検証。"""
import json
import sys
import numpy as np
from scipy.io import wavfile
from campaign import ROOT,PILOT,PRIOR,RESULT,digest,save
from revision_budget import RevisionBudget,REVISION
from acoustic_control import features,predict,decode,measure_wide,map_to_hts
sys.path.insert(0,str(PRIOR/'hts-bundle-v2'))
from japanese_frontend import analyze
from hts_core import render_hts
from acoustics import evaluate
sys.path.insert(0,str(PILOT/'.cache/packages'))
import pyworld

TEXTS=['虹が出た。','猫が眠る。','川を渡る。','鐘が響く。',
       '台所の棚から青い茶碗を取り出しました。','静かな公園で子供たちが落ち葉を集めています。',
       '夕食の前に畑で採れた野菜を丁寧に洗います。','駅まで歩いている途中で急に雨が降り始めました。',
       '砂が乾く。','星を探す。','朝日が昇る。','枝が揺れる。']


def prepare(budget):
    path=REVISION/'render-protocol.json'
    if path.exists():return json.loads(path.read_text())
    with budget.job('setup','改訂制御の未知8文と音響検査を固定',1000000):
        known=set()
        for p in [PRIOR/'splits.json',PRIOR/'hts-transfer/protocol.json',RESULT/'protocol.json',RESULT/'relative-protocol.json',RESULT/'bounded-protocol.json']:
            known.update(r['text'] for r in json.loads(p.read_text())['rows'])
        for name in ['runtime-audit/contract.json','hts-runtime-audit-v2/contract.json']:
            known.update(t if isinstance(t,str) else t['text'] for t in json.loads((PRIOR/name).read_text())['tests'])
        selected=[s for s in TEXTS if s not in known][:8]
        if len(selected)!=8:raise ValueError('未使用文が不足')
        conditions=[(180.,.85),(180.,1.15),(260.,.85),(260.,1.15)]
        rows=[]
        for i,text in enumerate(selected):
            f0,speed=conditions[i%4]
            rows.append({'id':f'acoustic-{i:02d}',**analyze(text),'challenge':{'requested_f0':f0,'speed':speed}})
        protocol={'rows':rows,'models':['native','direct_non_neural','neural_control','distilled_non_neural'],
                  'conditions':['neutral','challenge'],'planned_synthesis_calls':112,
                  'model_hashes':{p.name:digest(p) for p in (REVISION/'models').iterdir()},
                  'acoustic_diagnostic_tolerance':{'f0_relative':.05,'duration_relative':.10},
                  'neural_role':'研究用制御の比較のみ。最終実行bundleへ含めない',
                  'AI_content_evaluation':'未実施。枠がなく音響改善から内容合格を推論しない',
                  'perceptual_certification':False,'new_texts_frozen_before_render':True}
        save(path,protocol)
        return protocol


def main():
    budget=RevisionBudget();protocol=prepare(budget)
    for name,h in protocol['model_hashes'].items():
        if digest(REVISION/'models'/name)!=h:raise ValueError('凍結モデルの変更')
    with budget.job('setup','研究用ニューラル制御の読込',1000000):
        import torch
        from torch import nn
        torch.set_num_threads(2)
        net=nn.Sequential(nn.Linear(10,16),nn.Tanh(),nn.Linear(16,16),nn.Tanh(),nn.Linear(16,2))
        net.load_state_dict(torch.load(REVISION/'models/neural_control.pt',map_location='cpu',weights_only=True));net.eval()
    models={v:json.loads((REVISION/'models'/(v+'.json')).read_text()) for v in protocol['models'] if v!='native'}
    for row in protocol['rows']:
        for condition in protocol['conditions']:
            requested={'requested_f0':220.,'speed':1.} if condition=='neutral' else row['challenge']
            for variant in protocol['models']:
                path=REVISION/'render'/row['id']/condition/(variant+'.json')
                if path.exists():
                    rec=json.loads(path.read_text())
                    if digest(ROOT/rec['wav'])!=rec['wav_sha256']:raise ValueError('既存出力の変更')
                    continue
                with budget.job('render','音響量改訂/'+row['id']+'/'+condition+'/'+variant,3000000,count=1 if variant=='native' else 2):
                    target=None;base=None
                    if variant=='native':
                        settings={'speed':requested['speed'],'half_tone':float(12*np.log2(requested['requested_f0']/220)),'saturated':False}
                    else:
                        m=models[variant]
                        if variant=='neural_control':
                            x,bd=features(row);z=(x-np.array(m['x_mean']))/np.array(m['x_scale'])
                            with torch.no_grad():y=net(torch.tensor(z,dtype=torch.float32)).numpy()
                            target=decode(y*np.array(m['y_scale'])+np.array(m['y_mean']),bd,**requested)
                        else:target=predict(m,row,**requested)
                        base=measure_wide(render_hts(row,PRIOR/'hts-bundle-v2/mei_normal.htsvoice'))
                        settings=map_to_hts(target,base)
                    audio=render_hts(row,PRIOR/'hts-bundle-v2/mei_normal.htsvoice',settings['speed'],settings['half_tone'])
                    peak=float(np.max(abs(audio)));gain=min(1.,.95/peak) if peak else 1.
                    audio=(audio*gain).astype(np.float32);evaluation=evaluate(audio,{},24000)
                    measured=measure_wide(audio)
                    f0,t=pyworld.dio(audio.astype(float),24000,f0_floor=70.,f0_ceil=800.,frame_period=5.)
                    f0=pyworld.stonemask(audio.astype(float),f0,t,24000)
                    measured['dio_f0_hz']=float(np.median(f0[f0>0])) if np.any(f0>0) else None
                    path.parent.mkdir(parents=True,exist_ok=True);wav=path.with_suffix('.wav')
                    if wav.exists():raise FileExistsError('未記録出力を上書きしません')
                    wavfile.write(wav,24000,audio)
                    save(path,{'id':row['id'],'text':row['text'],'variant':variant,'condition':condition,'requested':requested,
                        'target':target,'calibration':base,'settings':settings,'measurement':measured,'evaluation':evaluation,
                        'raw_peak':peak,'output_gain':gain,'wav':str(wav.relative_to(ROOT)),'wav_sha256':digest(wav),
                        'runtime_neural_control':variant=='neural_control','synthesis_calls':1 if variant=='native' else 2,
                        'content_verified':False,'quality_certified':False})
                print(row['id'],condition,variant,evaluation['E0_pass'],settings['saturated'],flush=True)


if __name__=='__main__':main()
