#!/usr/bin/env python3
"""辞書アクセント・モーラ時間・短い舌尖接触をVTLで分離比較する。"""
import ctypes as ct
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.backends import VTL
from autonomous_speech_synthesis.io import read,write_once,file_hash
from campaign_v2 import BoundedCampaign
from vtl_speech import sampa_segments


def timed_segments(analysis,mora_seconds=.20):
    segments=[('',.05)];pitch=[(.05,False)];phone_times=[];time=.05;phone_cursor=0
    mapping={'sh':'S','ch':'tS','j':'dZ','y':'j','w':'u','r':'l','N':'N','I':'i','U':'u','A':'a','E':'e','O':'o'}
    for phrase in analysis['phrases']:
        if phrase.get('pause'):
            segments.append(('',.14));pitch.append((.14,False));time+=.14;phone_cursor+=1;continue
        allphones=analysis['phonemes']
        for mora in phrase['moras']:
            phones=mora['phones'];duration=mora_seconds
            if len(phones)>2:raise ValueError('3音素以上のモーラは未対応です')
            if phones==['Q']:
                # 後続子音を明示的に長くする。未知の後続文脈は除外する。
                following=allphones[phone_cursor+1] if phone_cursor+1<len(allphones) else ''
                if following not in ('p','t','k','s','sh','ch','ts'):raise ValueError('促音の後続文脈が未対応です')
                items=[(mapping.get(following,following),duration,'Q')]
            else:
                items=[]
                for p in phones:
                    d=duration if len(phones)==1 else duration*.3 if p!=phones[-1] else duration*.7
                    if p in ('ky','gy','ny','hy','my','ry','by','py'):
                        b={'ky':'k','gy':'g','ny':'n','hy':'h','my':'m','ry':'l','by':'b','py':'p'}[p]
                        items.extend([(b,d*.55,p),('j',d*.45,p)])
                    else:items.append((mapping.get(p,p),d,p))
            for s,d,p in items:
                segments.append((s,d));phone_times.append({'phone':p,'start':time,'end':time+d});time+=d
            pitch.append((duration,mora['high']));phone_cursor+=len(phones)
    segments.append(('',.1));pitch.append((.1,False))
    return segments,pitch,phone_times


def patch_taps(root,duration=.028):
    """側音区間の中央だけを短い有声の舌尖閉鎖へ置換。声門系列は保持する。"""
    seq=root.find("gesture_sequence[@type='tongue-tip-gestures']")
    n=0
    for g in list(seq):
        if 'lateral' not in g.get('value',''):continue
        total=float(g.get('duration_s'));width=min(duration,total)
        before=(total-width)/2;after=total-before-width
        index=list(seq).index(g);seq.remove(g)
        replacements=[]
        for d,value,neutral,tau in [(before,'',1,.007),(width,'tt-alveolar-closure',0,.007),(after,'',1,.007)]:
            if d>1e-8:replacements.append(ET.Element('gesture',value=value,slope='0',duration_s=f'{d:.8f}',time_constant_s=str(tau),neutral=str(neutral)))
        for j,item in enumerate(replacements):seq.insert(index+j,item)
        n+=1
    return n


def render_japanese(vtl,analysis,variant,seed):
    if variant=='baseline':
        segments=sampa_segments(analysis['phonemes'],.85);pitch=[];timing=[]
    else:segments,pitch,timing=timed_segments(analysis)
    with tempfile.TemporaryDirectory(prefix='ans-ja-v2-') as temp:
        temp=Path(temp);seg=temp/'text.seg';ges=temp/'generated.ges';wav=temp/'raw.wav'
        seg.write_text('\n'.join(f'name = {p}; duration_s = {d:.8f};' for p,d in segments)+'\n')
        vtl.lib.vtlSegmentSequenceToGesturalScore.argtypes=[ct.c_char_p,ct.c_char_p,ct.c_bool]
        vtl.lib.vtlGesturalScoreToAudio.argtypes=[ct.c_char_p,ct.c_char_p,ct.POINTER(ct.c_double),ct.POINTER(ct.c_int),ct.c_bool]
        vtl.check(vtl.lib.vtlSegmentSequenceToGesturalScore(str(seg).encode(),str(ges).encode(),False))
        tree=ET.parse(ges);root=tree.getroot();seq=root.find("gesture_sequence[@type='f0-gestures']")
        for g in list(seq):seq.remove(g)
        total=sum(d for _,d in segments);base=12*math.log2(160.)
        if variant in ('baseline','mora'):
            points=[(.12*total,-1.5),(.48*total,1.),(.40*total,-2.)]
        else:points=[(d,1.5 if high else -1.5) for d,high in pitch]
        for d,offset in points:ET.SubElement(seq,'gesture',value=f'{base+offset:.8f}',slope='0',duration_s=f'{d:.8f}',time_constant_s='.025',neutral='0')
        taps=patch_taps(root) if variant=='accent-tap' else 0
        tree.write(ges,encoding='unicode');score=ges.read_text()
        ct.CDLL(None).srand(ct.c_uint(seed))
        vtl.check(vtl.lib.vtlGesturalScoreToAudio(str(ges).encode(),str(wav).encode(),None,None,False))
        fs,x=wavfile.read(wav)
        if fs!=44100:raise ValueError('VTL標本化周波数が想定と異なります')
        audio=signal.resample_poly(x.astype(float)/32768,80,147)*.5
        fade=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,fade))**2
        audio[:fade]*=env;audio[-fade:]*=env[::-1]
        return audio,{'version':'vtl-japanese-gesture-v2','variant':variant,'phonemes':analysis['phonemes'],'phrase_moras':analysis['phrases'],'segments':segments,'phone_times':timing,'tap_gestures':taps,'gestural_score_generated_at_runtime':score,'f0_hz':160,'seed':seed,'backend':vtl.metadata,'limitations':['短い舌尖閉鎖は弾音の研究近似。側方流路や実測接触は未校正','非円唇uと無声化I/Uは未対応','句内二値F0は辞書アクセント規則の近似であり自然韻律認定なし']},24000


def main():
    config=read(ROOT/'config/campaign-v1.json')
    config.update(branch='日本語のモーラ時間、辞書アクセント、舌尖接触を一要素ずつ比較',model_version='vtl-japanese-gesture-v2',branch_sources={p:file_hash(ROOT/p) for p in ('vtl_japanese.py','campaign_v2.py','japanese_frontend.py','vtl_speech.py')})
    campaign=BoundedCampaign('ans-vtl-japanese-v2',config)
    records=read(ROOT/'results/frontend-v2/analysis.json')['records']
    tasks=[{'id':f'ja-{i:02d}','stage':'P4','kind':'sentence','text':r['text'],'phonemes':r['phonemes'],'frontend_split':r['split'],'analysis':r} for i,r in enumerate(records) if r['status']=='resolved']
    campaign.preflight_tasks(tasks)
    variants=['baseline','mora','accent','accent-tap']
    write_once(campaign.path/'model-registry.json',{'id':'vtl-japanese-gesture-v2','parent':'vtl-jd3-v1','allowed_extensions':['mora-timing','dictionary-accent','short-tongue-tip-contact'],'runtime_neural':False,'source_hashes':config['branch_sources']})
    write_once(campaign.path/'task-suite.json',{'tasks':tasks})
    write_once(campaign.path/'splits.json',read(ROOT/'results/ans-pilot-v1/splits.json'))
    write_once(campaign.path/'frozen-config.json',{'variants':variants,'task_count':len(tasks),'seeds':[41,43],'f0_hz':160,'mora_seconds':.20,'tap_seconds':.028,'scope':'開発と新規文脈の診断。最終確認参照を使用しない。','selection':'ASRは診断、知覚昇格はしない'})
    vtl=VTL();results=[]
    try:
        for variant in variants:
            for task in tasks:
                for seed in (41,43):
                    result=campaign.trial(variant,'vtl','P4',task,seed,{'variant':variant,'f0_hz':160,'mora_seconds':.20,'tap_seconds':.028},lambda t=task,v=variant,s=seed:render_japanese(vtl,t['analysis'],v,s),save=seed==41)
                    results.append({'variant':variant,'task':task['id'],'kind':'sentence','seed':seed,'trial_id':result['trial_id'],'evaluation':result['evaluation'],'wav':result.get('wav')})
                print(variant,task['id'],flush=True)
        write_once(campaign.path/'p34-speech.json',{'rows':results,'quality_status':'inconclusive','backend':'vtl','limitations':'日本語調音と知覚代理の資格は未取得'})
        write_once(campaign.path/'decision.json',{'state':'inconclusive','quality_goal_achieved':False,'renders':len(results),'E0_failed':sum(not r['evaluation']['E0_pass'] for r in results),'reason':'E1/E2資格不足。全体完了条件は未達。'})
    finally:vtl.close();campaign.close()


if __name__=='__main__':main()
