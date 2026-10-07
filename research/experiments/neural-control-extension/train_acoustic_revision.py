"""既存教師の波形上の時間・F0を学ぶ。合成器の指令値を教師に混ぜない。"""
import json
import sys
import numpy as np
from scipy.io import wavfile
from campaign import ROOT, PILOT, PRIOR, RESULT, digest, save
from revision_budget import RevisionBudget, REVISION
from acoustic_control import features, FEATURE_NAMES
from teacher_alignment import align_saved
sys.path.insert(0,str(PILOT/'.cache/packages'))
import pyworld


def prepare(budget):
    if (REVISION/'targets.json').exists():
        return json.loads((REVISION/'targets.json').read_text())
    with budget.job('setup','音響量の再学習仕様と既存資料の分割を固定',3000000):
        if not (REVISION/'protocol.json').exists():
            save(REVISION/'protocol.json', {'scope':'同一campaignの未使用レンダー枠のみ。追加ASRと教師生成なし',
                'features':FEATURE_NAMES,'quantity':'波形で測った活動長と有声F0中央値',
                'training':'旧開発12文＋追加jf_alphaのunknown-00〜09（誤読08を除く）',
                'selection':'旧選別6文＋追加jf_alphaのunknown-10〜15',
                'data_status':'いずれも研究で既知の資料。新規品質確認には使わない',
                'models':['direct_non_neural','neural_control','distilled_non_neural'],
                'ridge_alphas':[.1,1.,10.,100.], 'neural_hidden':[16,16], 'epochs':[250,500,1000],
                'selection_loss':'標準化した対数活動長比と対数F0比の平均二乗誤差',
                'control':'指定F0比・速度は予測後に明示的に適用。文長の単独回帰項を使わない',
                'hts_bounds':{'speed':[.5,2.],'half_tone':[-12.,12.]},
                'planned_render_calls':128,'runtime_equality_pairs':4,
                'perceptual_or_content_certification':False})
        old = [r for r in json.loads((PRIOR/'splits.json').read_text())['rows'] if r['split'] in ('development','selection')]
        newer = json.loads((RESULT/'protocol.json').read_text())['rows']
        sources = []
        for r in old:
            p = PRIOR/'teacher'/f"{r['id']}.json"
            corrected = PRIOR/'teacher-corrected'/f"{r['id']}.json"
            if corrected.exists():p=corrected
            sources.append((r,r['split'],p,PILOT))
        for i,r in enumerate(newer):
            if i==8:continue
            sources.append((r,'development' if i<10 else 'selection',RESULT/'teacher/jf_alpha'/f"{r['id']}.json",ROOT))
        rows=[]
        for analysis, split, p, base in sources:
            teacher=json.loads(p.read_text());wav=base/teacher['wav']
            if digest(wav)!=teacher['wav_sha256']:raise ValueError('教師のハッシュ不一致')
            # 対応の検査は誤読を除くため。内部時刻を音響時間としては学習しない。
            _,_,equivalences=align_saved(analysis,teacher)
            fs,audio=wavfile.read(wav);audio=audio.astype(np.float64)
            hop=round(.01*fs)
            rms=np.array([np.sqrt(np.mean(audio[j:j+hop]**2)) for j in range(0,len(audio),hop)])
            active=np.flatnonzero(rms>max(1e-5,.05*rms.max()))
            if not len(active):raise ValueError('教師の活動区間がない')
            start,end=active[0]*hop,min(len(audio),(active[-1]+1)*hop)
            f0,t=pyworld.dio(audio,fs,f0_floor=70.,f0_ceil=800.,frame_period=5.)
            f0=pyworld.stonemask(audio,f0,t,fs)
            voiced=f0[(f0>0)&(t>=start/fs)&(t<end/fs)]
            if not len(voiced):raise ValueError('教師のF0がない')
            x,bd=features(analysis);duration=float((end-start)/fs);pitch=float(np.median(voiced))
            rows.append({'id':analysis['id'],'text':analysis['text'],'split':split,'x':x.tolist(),
                'y':[float(np.log(duration/bd)),float(np.log(pitch/220.))], 'active_seconds':duration,'f0_hz':pitch,
                'baseline_seconds':bd,'phone_count':len(analysis['phonemes']),'equivalences':equivalences,
                'wav_sha256':digest(wav),'source':str(p),'actuator_fit_used':False})
        result={'rows':rows,'counts':{s:sum(r['split']==s for r in rows) for s in ['development','selection']},
                'method':'活動区間RMS・WORLD DIO/StoneMask。局所境界と知覚評価の資格は与えない'}
        save(REVISION/'targets.json',result)
        return result


def ridge(x,y,alpha):
    penalty=np.eye(x.shape[1])*alpha;penalty[0,0]=0
    return np.linalg.solve(x.T@x+penalty,x.T@y)


def main():
    budget=RevisionBudget();dataset=prepare(budget)
    if (REVISION/'model-selection.json').exists():raise FileExistsError('凍結済みのモデル選択を再学習しません')
    with budget.job('train','波形由来の音響量を直接学習・ニューラル学習・蒸留',3000000):
        import torch
        from torch import nn
        torch.set_num_threads(2);torch.manual_seed(20261002)
        def data(split):
            rows=[r for r in dataset['rows'] if r['split']==split]
            return np.array([r['x'] for r in rows]),np.array([r['y'] for r in rows])
        x,y=data('development');vx,vy=data('selection')
        xm,xs=x.mean(0),x.std(0);xs[xs<1e-6]=1;xm[0]=0;xs[0]=1
        ym,ys=y.mean(0),y.std(0);ys[ys<1e-6]=1
        x,vx=(x-xm)/xs,(vx-xm)/xs;y,vy=(y-ym)/ys,(vy-ym)/ys
        def candidates(target):
            out=[]
            for alpha in [.1,1.,10.,100.]:
                coefficients=ridge(x,target,alpha);score=float(np.mean((vx@coefficients-vy)**2))
                out.append({'alpha':alpha,'score':score,'coefficients':coefficients})
            return out
        direct=candidates(y)
        net=nn.Sequential(nn.Linear(10,16),nn.Tanh(),nn.Linear(16,16),nn.Tanh(),nn.Linear(16,2))
        optimizer=torch.optim.Adam(net.parameters(),lr=.003,weight_decay=.01)
        tx,ty,tvx=map(lambda a:torch.tensor(a,dtype=torch.float32),[x,y,vx]);checks=[]
        for epoch in range(1,1001):
            optimizer.zero_grad();loss=((net(tx)-ty)**2).mean();loss.backward();optimizer.step()
            if epoch in (250,500,1000):
                with torch.no_grad():score=float(np.mean((net(tvx).numpy()-vy)**2))
                checks.append({'epoch':epoch,'score':score,'state':{k:v.detach().clone() for k,v in net.state_dict().items()}})
        best=min(checks,key=lambda r:r['score']);net.load_state_dict(best['state']);net.eval()
        with torch.no_grad():student=candidates(net(tx).numpy())
        normalization={'x_mean':xm.tolist(),'x_scale':xs.tolist(),'y_mean':ym.tolist(),'y_scale':ys.tolist()}
        chosen={}
        for variant,options in [('direct_non_neural',direct),('distilled_non_neural',student)]:
            selected=min(options,key=lambda r:r['score'])
            model={**normalization,'type':'ridge','quantity':'acoustic-active-duration-and-f0','features':FEATURE_NAMES,
                   'coefficients':selected['coefficients'].tolist(),'alpha':selected['alpha'],'source_targets_sha256':digest(REVISION/'targets.json')}
            save(REVISION/'models'/(variant+'.json'),model)
            chosen[variant]={'alpha':selected['alpha'],'selection_loss':selected['score']}
        nnpath=REVISION/'models/neural_control.pt';torch.save(net.state_dict(),nnpath)
        save(REVISION/'models/neural_control.json',{**normalization,'type':'neural','quantity':'acoustic-active-duration-and-f0','research_only':True,'weights_sha256':digest(nnpath)})
        chosen['neural_control']={'epoch':best['epoch'],'selection_loss':best['score']}
        save(REVISION/'model-selection.json',{'chosen':chosen,'frozen_before_new_render':True,'targets_sha256':digest(REVISION/'targets.json'),
             'development_utterances':len(x),'selection_utterances':len(vx),'features':10,
             'candidates':{'direct':[{'alpha':r['alpha'],'score':r['score']} for r in direct],
                           'neural':[{'epoch':r['epoch'],'score':r['score']} for r in checks],
                           'distilled':[{'alpha':r['alpha'],'score':r['score']} for r in student]},'quality_adoption':False})
        print(json.dumps(chosen,ensure_ascii=False))


if __name__=='__main__':main()
