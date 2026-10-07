#!/usr/bin/env python3
"""追加サイクル最終枠。粗格子と局所適合を組み合わせ、新しい目標で資格確認する。"""
import itertools
from spectral_fit_v1 import *


def qualify(c,base,tasks):
    out=c.path/'qualification.json'
    if out.exists():return read(out)
    parent=read(ROOT/'results/ans-spectral-fit-v1/qualification.json')
    if not all(r['passed'] for r in parent['parity']):raise ValueError('高速経路の一致資格がありません')
    task=next(t for t in tasks if t['id']=='vowel-a-220')
    truth=np.array([.57,.36,.64,.44,.58]);seed=79
    _,y=evaluate_point(c,task,base,truth,seed,'P1','fresh-target')
    fits=[]
    for name,initial,nfev in [('near',truth+.025,3),('far',np.array([.85,.15,.20,.72,.22]),8)]:
        calls=[]
        def fun(z):
            row,feat=evaluate_point(c,task,base,z,seed,'P1',f'recovery-{name}-{len(calls):03d}')
            delta=feat-y;calls.append({'point':z.tolist(),'rmse':float(np.sqrt(np.mean(delta**2))),'trial':row['trial_id']});return delta
        if name=='far':
            fun(initial)
            for frequencies in itertools.product((.2,.5,.8),repeat=3):fun(np.r_[frequencies,.5,.5])
            initial=np.array(min(calls,key=lambda r:r['rmse'])['point'])
        fit=least_squares(fun,initial,bounds=(0,1),max_nfev=nfev,diff_step=1e-3,ftol=1e-8,xtol=1e-8,gtol=1e-8)
        best=min(calls,key=lambda r:r['rmse'])
        fits.append({'start':name,'calls':len(calls),'best':best,'coefficient_max_error':float(max(abs(np.asarray(best['point'])-truth))),
                     'passed':best['rmse']<=.015,'optimizer_status':fit.status})
    q={'passed':all(r['passed'] for r in fits),'fits':fits,'truth':truth.tolist(),'threshold_log10_rmse':.015,
       'prior_parity_sha256':file_hash(ROOT/'results/ans-spectral-fit-v1/qualification.json'),
       'scope':'凍結した高速経路と新しい/a/220Hz目標の近傍・遠方自己回復。遠方は27格子を併用。自然さ・全母音での大域収束は未資格。'}
    write_once(out,q);return q

def main():
    config=read(ROOT/'config/campaign-v1.json')
    config.update(branch='27格子と局所適合による5変数・平滑対数スペクトルの条件別適合',branch_sources={p:file_hash(ROOT/p) for p in
                  ('spectral_multistart_v1.py','spectral_fit_v1.py','cycle_campaign_v1.py','campaign_v2.py','free_fit_bounds_v2.py')})
    c=CycleCampaign('ans-spectral-multistart-v1',config)
    parent=ROOT/'results/ans-pilot-v1';base=read(parent/'voice-config.json')
    tasks=[t for t in read(parent/'task-suite.json')['tasks'] if t['stage']=='P2']
    frozen={'source_voice_sha256':file_hash(parent/'voice-config.json'),'dimensions':5,'fixed_gain_index':0,
            'objective':'80〜5500Hz、1024点Welch、94Hz標準偏差のGaussian平滑後の正規化対数パワー',
            'self_recovery_truth':[.57,.36,.64,.44,.58], 'coarse_grid':[.2,.5,.8], 'coarse_gain_point':[.5,.5],'self_recovery_threshold':.015,'self_recovery_max_nfev':[3,8],
            'natural_fit_max_nfev_per_start':8,'natural_fit_starts':2,'natural_fit_seed':11,
            'recheck_seeds':[101,103,107],'max_qualification_renders':100,'allow_export':False,
            'known_limitations':['短い自然母音と合成定常区間の時間分解能差','参照F0許容幅30%','位相・知覚・動的発話は目的外'],
            'qualification_scope':'/a/220Hzで合格後、他母音は収束を保証しない研究診断として比較する'}
    try:
        write_once(c.path/'frozen-config.json',frozen);write_once(c.path/'task-suite.json',{'tasks':tasks})
        q=qualify(c,base,tasks);print('自己回復',q['passed'],q['fits'],flush=True)
        if not q['passed']:
            write_once(c.path/'decision.json',{'state':'inconclusive','quality_goal_achieved':False,'reason':'新目的での自己回復が不通過。自然参照へ適合しない。'});return
        refs={}
        for group in ('development','selection'):
            p=c.path/f'reference-spectral-{group}.json'
            refs[group]=read(p) if p.exists() else reference_spectra(parent,group)
            write_once(p,refs[group])
        results=[];rng=np.random.default_rng(20261003)
        for task in tasks:
            vowel=task['phonemes'][0]
            target,speakers=target_spectrum(refs['development'],vowel,task['f0_hz'])
            selected,selection_speakers=target_spectrum(refs['selection'],vowel,task['f0_hz'])
            if target is None or selected is None:
                results.append({'task':task['id'],'status':'out-of-domain','development_speakers':speakers,'selection_speakers':selection_speakers});continue
            # 基準周波数を順序保存写像の逆写像へ戻す。
            low=np.array(voice_from_point(base,vowel,np.zeros(5))['formants_hz'][vowel])
            high=np.array(voice_from_point(base,vowel,np.ones(5))['formants_hz'][vowel])
            initial=np.r_[(np.array(base['formants_hz'][vowel])-low)/(high-low),(np.array(base['formant_gains'][1:])-.05)/.95]
            calls=[]
            def fun(z):
                row,feat=evaluate_point(c,task,base,z,11,'P2',f'fit-{len(calls):03d}')
                delta=feat-target;calls.append({'point':z.tolist(),'loss':float(np.mean(delta**2)),'trial':row['trial_id']});return delta
            fun(initial)
            for frequencies in itertools.product((.2,.5,.8),repeat=3):fun(np.r_[frequencies,.5,.5])
            grid_start=np.array(min(calls,key=lambda r:r['loss'])['point'])
            for start in (initial,grid_start):
                least_squares(fun,start,bounds=(0,1),max_nfev=8,diff_step=1e-3,ftol=1e-7,xtol=1e-7,gtol=1e-7)
            best=min(calls,key=lambda r:r['loss']);checks=[]
            for kind,z in [('shared',initial),('free',best['point'])]:
                for seed in (101,103,107):
                    row,feat=evaluate_point(c,task,base,z,seed,'P2-recheck',kind)
                    checks.append({'kind':kind,'seed':seed,'selection_loss':float(np.mean((feat-selected)**2)),'trial':row['trial_id']})
            results.append({'task':task['id'],'status':'diagnostic-only','shared_development_loss':calls[0]['loss'],
                            'free_development_loss':best['loss'],'best_point':best['point'],'evaluations':len(calls),
                            'development_speakers':speakers,'selection_speakers':selection_speakers,'selection':checks})
            print(task['id'],calls[0]['loss'],best['loss'],flush=True)
        write_once(c.path/'comparison.json',{'rows':results,'export_allowed':False,'qualification':q['scope']})
        write_once(c.path/'decision.json',{'state':'inconclusive','quality_goal_achieved':False,'reason':'静的スペクトル適合の機構診断のみ。E1/E2と動的発話の品質資格は未達。'})
    finally:c.close()

if __name__=='__main__':main()
