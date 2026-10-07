#!/usr/bin/env python3
"""研究専用の条件別声道適合と、凍結した共有規則を比較する。"""
import copy
import json
from pathlib import Path
import sys
import numpy as np
from scipy.optimize import least_squares
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT))
from autonomous_speech_synthesis.io import read,write_once,file_hash
from autonomous_speech_synthesis.generator import render
from autonomous_speech_synthesis.data import target_bands
from autonomous_speech_synthesis.search import residual
from autonomous_speech_synthesis.runner import BudgetExhausted
from campaign_v2 import BoundedCampaign


class FreeFitCampaign(BoundedCampaign):
    def budget_check(self,stage,backend):
        key=super().budget_check(stage,backend)
        if stage=='P1':
            key='max_p1_renders'
            if sum(e['event']=='started' and e.get('budget_key')==key for e in self.events)>=self.config['budget'][key]:raise BudgetExhausted('自己回復のレンダー上限です')
        return key


class CellBudget(RuntimeError):pass


def voice_from_point(base,vowel,z):
    v=copy.deepcopy(base)
    v['formants_hz'][vowel]=(np.array(base['formants_hz'][vowel])*(.85+.30*np.asarray(z[:3]))).tolist()
    v['formant_gains']=(.05+.95*np.asarray(z[3:])).tolist()
    return v


def generate(task,voice,seed):
    x,log=render(task['phonemes'],task['prosody'],voice,seed)
    return x,log,24000


def features(row):
    if not row['evaluation']['E0_pass']:raise ValueError('適合中の信号検査が不通過です')
    return np.log10(np.maximum(row['evaluation']['E1']['features']['band_energy_fractions'],1e-6))


def qualify(campaign,base,task):
    out=campaign.path/'free-fit-qualification.json'
    if out.exists():return read(out)
    truth=np.array([.65,.35,.55,.72,.5,.33]);seed=17
    target=campaign.trial('recovery-target','dsp','P1',task,seed,{'point':truth.tolist()},lambda:generate(task,voice_from_point(base,'a',truth),seed))
    y=features(target);results=[]
    for name,initial,nfev in [('near',np.clip(truth+.03,0,1),5),('far',np.array([.2,.8,.2,.35,.8,.65]),8)]:
        calls=[]
        def fun(z):
            row=campaign.trial(f'recovery-{name}-{len(calls):03d}','dsp','P1',task,seed,{'point':z.tolist()},lambda:generate(task,voice_from_point(base,'a',z),seed))
            delta=features(row)-y;calls.append({'point':z.tolist(),'error':float(np.sqrt(np.mean(delta**2))),'trial':row['trial_id']});return delta
        fit=least_squares(fun,initial,bounds=(0,1),max_nfev=nfev,diff_step=1e-3,ftol=1e-7,xtol=1e-7,gtol=1e-7)
        best=min(calls,key=lambda r:r['error'])
        results.append({'start':name,'calls':len(calls),'best':best,'passed':best['error']<=.015,'optimizer_status':fit.status})
    result={'passed':all(r['passed'] for r in results),'rows':results,'response_rmse_log10_threshold':.015,'coefficient_recovery_required':False,'scope':'同じ6自由度・同じ5帯域残差による生成済み音響応答の回復。自然さ資格ではない。'}
    write_once(out,result);return result


def main():
    config=read(ROOT/'config/campaign-v1.json')
    config.update(branch='標本内oracleしかなかったP2に、条件別6自由度の実適合を追加する',branch_sources={p:file_hash(ROOT/p) for p in ('free_fit.py','campaign_v2.py')},model_version='dsp-lf-gesture-v1-research-free-fit')
    c=FreeFitCampaign('ans-free-fit-v1',config)
    parent=ROOT/'results/ans-pilot-v1';base=read(parent/'voice-config.json');suite=read(parent/'task-suite.json')
    tasks=[t for t in suite['tasks'] if t['stage']=='P2']
    write_once(c.path/'task-suite.json',{'tasks':tasks});write_once(c.path/'splits.json',read(parent/'splits.json'))
    write_once(c.path/'model-registry.json',{'id':'dsp-lf-gesture-v1-research-free-fit','parent':'dsp-lf-gesture-v1','free_parameters':'母音/F0セルごとのF1/F2/F3と3共鳴器利得。音源は凍結。','allowed_export':False})
    frozen={'starts':2,'max_nfev_per_start':8,'max_evaluations_per_cell':112,'seeds':[11,23,37],'recheck_seeds':[101,103,107],'free_dimensions_per_cell':6,'formant_multiplier_bounds':[.85,1.15],'gain_bounds':[.05,1.],'objective':'開発話者均等の対数5帯域残差','qualification_threshold_rmse_log10':.015,'comparison':'同一開発目的への適合能力と選別群での残差。自由適合は条件固有の研究診断であり移出しない。','reference_hashes':{p:file_hash(parent/p) for p in ('reference-development.json','reference-selection.json','voice-config.json')}}
    write_once(c.path/'frozen-config.json',frozen)
    try:
        q=qualify(c,base,next(t for t in tasks if t['id']=='vowel-a-220'))
        print('自己回復',q['passed'],flush=True)
        if not q['passed']:
            write_once(c.path/'decision.json',{'state':'inconclusive','quality_goal_achieved':False,'reason':'同じ自由適合問題の自己回復が閾値未達。自然参照への適合を開始しない。'});return
        development=read(parent/'reference-development.json');selection=read(parent/'reference-selection.json')
        summary=[];rng=np.random.default_rng(20261002)
        initial=np.r_[[.5]*3,(np.array(base['formant_gains'])-.05)/.95]
        for task in tasks:
            target,coverage=target_bands(development,task['phonemes'][0],task['f0_hz']);selected,selected_coverage=target_bands(selection,task['phonemes'][0],task['f0_hz'])
            if target is None or selected is None:
                summary.append({'task':task['id'],'status':'out-of-domain','coverage':coverage,'selection_coverage':selected_coverage});continue
            target=np.log10(np.maximum(target,1e-6));calls=[]
            shared=[]
            for seed in (11,23,37):
                row=c.trial('shared','dsp','P2',task,seed,{'voice':base},lambda s=seed:generate(task,base,s))
                shared.append(float(np.mean((features(row)-target)**2)))
            def fun(z):
                if len(calls)>=112:raise CellBudget('セルの112評価上限です')
                voice=voice_from_point(base,task['phonemes'][0],z);measures=[];ids=[]
                for seed in (11,23,37):
                    row=c.trial(f'free-{task["id"]}-{len(calls):03d}','dsp','P2',task,seed,{'point':z.tolist()},lambda s=seed:generate(task,voice,s))
                    measures.append(features(row));ids.append(row['trial_id'])
                delta=np.mean(measures,axis=0)-target
                calls.append({'point':z.tolist(),'loss':float(np.mean(delta**2)),'trials':ids});return delta
            # 共有点を必ず候補に含め、遠い開始点も固定seedで用意する。
            for start in (initial,rng.uniform(.1,.9,6)):
                try:least_squares(fun,start,bounds=(0,1),max_nfev=8,diff_step=1e-3,ftol=1e-7,xtol=1e-7,gtol=1e-7)
                except CellBudget:break
            best=min(calls,key=lambda r:r['loss']);v=voice_from_point(base,task['phonemes'][0],best['point']);check=[]
            for kind,voice in [('shared',base),('free',v)]:
                for seed in (101,103,107):
                    row=c.trial(kind+'-recheck','dsp','P2-recheck',task,seed,{'voice':voice},lambda v=voice,s=seed:generate(task,v,s),save=seed==101)
                    check.append({'kind':kind,'seed':seed,'residual':residual(row,selected),'trial':row['trial_id']})
            summary.append({'task':task['id'],'shared_development_loss':float(np.mean(shared)),'free_development_loss':best['loss'],'best_point':best['point'],'evaluations':len(calls),'selection':check,'coverage':coverage,'selection_coverage':selected_coverage})
            print(task['id'],summary[-1]['shared_development_loss'],best['loss'],flush=True)
        write_once(c.path/'free-fit-comparison.json',{'rows':summary,'status':'diagnostic-only','export_allowed':False,'scope':'5帯域・条件別静的声道の適合能力。時変軌跡や知覚的な自由適合の上限ではない。係数を未知文へ転用しない。'})
        write_once(c.path/'decision.json',{'state':'inconclusive','quality_goal_achieved':False,'reason':'自由適合と共有規則の能力診断。必須知覚ゲートの資格不足を変更しない。','cells':len(summary)})
    finally:c.close()


if __name__=='__main__':main()
