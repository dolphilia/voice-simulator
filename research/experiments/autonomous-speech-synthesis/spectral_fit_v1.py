#!/usr/bin/env python3
"""正規化スペクトルの5自由度適合。全波形評価を追記台帳へ計上する。"""
import copy
import sys
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from scipy.io import wavfile
from scipy.optimize import least_squares
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,file_hash,REPO
from autonomous_speech_synthesis.generator import render,lf_source
from autonomous_speech_synthesis.gestures import make_gestures
from cycle_campaign_v1 import CycleCampaign
from free_fit_bounds_v2 import voice_from_point as six_voice


def voice_from_point(base,vowel,z):
    # 正規化スペクトルでは全体利得が不可視なので第1共鳴器利得を固定する。
    z=np.asarray(z)
    if z.shape!=(5,): raise ValueError('適合点は5変数です')
    return six_voice(base,vowel,np.r_[z[:3],(base['formant_gains'][0]-.05)/.95,z[3:]])


def static_render(task,voice,seed):
    """単一・通常有声母音のみ。一定係数のfilter処理を一括し、既存波形と照合する。"""
    if len(task['phonemes'])!=1 or task['phonemes'][0] not in 'aiueo':
        raise ValueError('高速経路の資格は単独の有声母音に限定します')
    fs=24000
    tracks,events=make_gestures(task['phonemes'],task['prosody'],voice,fs)
    if not np.all(tracks['formants_hz']==tracks['formants_hz'][0]) or np.any(tracks['noise']) or np.any(tracks['nasal']):
        raise ValueError('時変声道・雑音・鼻腔は高速経路の範囲外です')
    rng=np.random.default_rng(seed)
    source=lf_source(tracks['f0_hz'],fs,voice['source'])
    source*=tracks['voicing']*tracks['gain']
    source+=rng.standard_normal(len(source))*voice['source']['aspiration']*tracks['voicing']*tracks['gain']
    out=np.zeros(len(source))
    for j,freq in enumerate(tracks['formants_hz'][0]):
        b,a=signal.iirpeak(freq,freq/(voice['bandwidths_hz'][j]*voice['bandwidth_scale']),fs=fs)
        out+=voice['formant_gains'][j]*signal.lfilter(b,a,source)
    out*=voice['gain']
    fade=min(round(.012*fs),len(out)//2)
    envelope=np.sin(np.linspace(0,np.pi/2,fade))**2
    out[:fade]*=envelope;out[-fade:]*=envelope[::-1]
    return out,{'version':'static-lti-v1','events':events,'seed':seed,'contains_recording':False,'runtime_neural_inference':False},fs


def spectral_features(audio,fs=24000):
    audio=np.asarray(audio,dtype=float)
    if len(audio)<256 or not np.all(np.isfinite(audio)):raise ValueError('スペクトル観測長が不足または非有限です')
    f,p=signal.welch(audio,fs,nperseg=min(1024,len(audio)),nfft=1024)
    p=gaussian_filter1d(p,4.,mode='nearest')
    use=(f>=80)&(f<=5500)
    p=p[use];p/=max(float(p.sum()),1e-30)
    return np.log10(np.maximum(p,1e-10))


def features(c,row):
    if not row['evaluation']['E0_pass']:raise ValueError('信号検査が不通過です')
    fs,x=wavfile.read(c.path/row['wav'])
    trim=min(round(.06*fs),len(x)//5)
    return spectral_features(x[trim:-trim],fs)


def evaluate_point(c,task,base,z,seed,stage,candidate):
    voice=voice_from_point(base,task['phonemes'][0],z)
    row=c.trial(candidate,'dsp',stage,task,seed,{'point':list(z),'dimensions':5},
                lambda:static_render(task,voice,seed),save=True)
    return row,features(c,row)


def qualify(c,base,tasks):
    out=c.path/'qualification.json'
    if out.exists():return read(out)
    parity=[]
    for vowel in 'aiueo':
        task=next(t for t in tasks if t['id']==f'vowel-{vowel}-220')
        row=c.trial('parity-core','dsp','P1',task,71,{'voice':base},lambda t=task:(*render(t['phonemes'],t['prosody'],base,71),24000),save=True)
        fast=c.trial('parity-fast','dsp','P1',task,71,{'voice':base},lambda t=task:static_render(t,base,71),save=True)
        _,x=wavfile.read(c.path/row['wav']);_,y=wavfile.read(c.path/fast['wav'])
        parity.append({'vowel':vowel,'max_abs_error':float(np.max(abs(x-y))),
                       'float64_hash_equal':row['audio_sha256']==fast['audio_sha256'],
                       'passed':row['audio_sha256']==fast['audio_sha256']})
    task=next(t for t in tasks if t['id']=='vowel-a-220')
    truth=np.array([.62,.29,.43,.61,.35]);seed=73
    target,y=evaluate_point(c,task,base,truth,seed,'P1','fresh-target')
    # 旧5帯域と新スペクトルを同じ5変数の数値ヤコビアンで比較する。
    old=np.log10(np.maximum(target['evaluation']['E1']['features']['band_energy_fractions'],1e-10))
    old_j=[];new_j=[]
    for j in range(5):
        point=truth.copy();point[j]+=.001
        row,feat=evaluate_point(c,task,base,point,seed,'P1',f'sensitivity-{j}')
        old_j.append((np.log10(np.maximum(row['evaluation']['E1']['features']['band_energy_fractions'],1e-10))-old)/.001)
        new_j.append((feat-y)/.001)
    sensitivity={}
    for name,matrix in [('old_bands',old_j),('spectral',new_j)]:
        values=np.linalg.svd(np.asarray(matrix).T,compute_uv=False)
        sensitivity[name]={'singular_values':values.tolist(),'effective_rank_rtol_1e-3':int(sum(values>values[0]*1e-3))}
    fits=[]
    for name,initial,nfev in [('near',truth+.025,5),('far',np.array([.25,.70,.8,.25,.75]),8)]:
        calls=[]
        def fun(z):
            row,feat=evaluate_point(c,task,base,z,seed,'P1',f'recovery-{name}-{len(calls):03d}')
            delta=feat-y
            calls.append({'point':z.tolist(),'rmse':float(np.sqrt(np.mean(delta**2))),'trial':row['trial_id']})
            return delta
        fit=least_squares(fun,initial,bounds=(0,1),max_nfev=nfev,diff_step=1e-3,ftol=1e-8,xtol=1e-8,gtol=1e-8)
        best=min(calls,key=lambda r:r['rmse'])
        fits.append({'start':name,'calls':len(calls),'best':best,'coefficient_max_error':float(max(abs(np.asarray(best['point'])-truth))),
                     'passed':best['rmse']<=.015,'optimizer_status':fit.status})
    q={'passed':all(p['passed'] for p in parity) and all(r['passed'] for r in fits),
       'parity':parity,'sensitivity':sensitivity,'fits':fits,'truth':truth.tolist(),
       'threshold_log10_rmse':.015,'scope':'単独有声母音の高速経路と/a/220Hzの近傍・遠方自己回復。自然さ・全母音での大域収束は未資格。'}
    write_once(out,q);return q


def reference_spectra(parent,group):
    if group not in ('development','selection'):raise PermissionError('最終確認群は開封しません')
    frozen=read(parent/f'reference-{group}.json')
    splits=read(parent/'splits.json');records={r['id']:r for r in splits['groups'][group]['records']}
    cache={};result=[]
    for row in frozen['rows']:
        key=row['id'];record=records[key]
        if key not in cache:
            p=REPO/record['wav']
            if file_hash(p)!=record['sha256'] or file_hash(REPO/record['lab'])!=record['label_sha256']:
                raise ValueError('参照資産のハッシュ不一致です')
            fs,x=wavfile.read(p)
            x=x.astype(float)/(max(abs(np.iinfo(x.dtype).min),np.iinfo(x.dtype).max) if np.issubdtype(x.dtype,np.integer) else 1.)
            if x.ndim==2:x=x.mean(axis=1)
            cache[key]=(fs,x)
        fs,x=cache[key];lo=round((row['start_seconds']+.015)*fs);hi=round((row['end_seconds']-.015)*fs)
        a=x[lo:hi];g=np.gcd(fs,24000);a=signal.resample_poly(a,24000//g,fs//g)
        result.append({'id':key,'speaker':row['speaker'],'vowel':row['vowel'],'f0_hz':row['features']['f0_hz'],
                       'features':spectral_features(a).tolist(),'effective_segment_samples':len(a)})
    return {'split':group,'rows':result,'source_sha256':file_hash(parent/f'reference-{group}.json')}


def target_spectrum(reference,vowel,f0):
    groups={}
    for row in reference['rows']:
        if row['vowel']==vowel and abs(np.log(row['f0_hz']/f0))<np.log(1.3):
            groups.setdefault(row['speaker'],[]).append(row['features'])
    return (np.mean([np.mean(v,axis=0) for v in groups.values()],axis=0) if len(groups)>=2 else None),sorted(groups)


def main():
    config=read(ROOT/'config/campaign-v1.json')
    config.update(branch='5変数・平滑対数スペクトルの条件別適合',branch_sources={p:file_hash(ROOT/p) for p in
                  ('spectral_fit_v1.py','cycle_campaign_v1.py','campaign_v2.py','free_fit_bounds_v2.py')})
    c=CycleCampaign('ans-spectral-fit-v1',config)
    parent=ROOT/'results/ans-pilot-v1';base=read(parent/'voice-config.json')
    tasks=[t for t in read(parent/'task-suite.json')['tasks'] if t['stage']=='P2']
    frozen={'source_voice_sha256':file_hash(parent/'voice-config.json'),'dimensions':5,'fixed_gain_index':0,
            'objective':'80〜5500Hz、1024点Welch、94Hz標準偏差のGaussian平滑後の正規化対数パワー',
            'self_recovery_truth':[.62,.29,.43,.61,.35],'self_recovery_threshold':.015,'self_recovery_max_nfev':[5,8],
            'natural_fit_max_nfev_per_start':15,'natural_fit_starts':2,'natural_fit_seed':11,
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
            for start in (initial,rng.uniform(.15,.85,5)):
                least_squares(fun,start,bounds=(0,1),max_nfev=15,diff_step=1e-3,ftol=1e-7,xtol=1e-7,gtol=1e-7)
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
