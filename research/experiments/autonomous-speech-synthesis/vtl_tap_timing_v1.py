#!/usr/bin/env python3
"""舌尖閉鎖の幅を保持し、接触時刻だけを比較する追加サイクル。"""
import ctypes as ct
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
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT))
from autonomous_speech_synthesis.io import read,write_once,file_hash
from autonomous_speech_synthesis.backends import VTL
from cycle_campaign_v1 import CycleCampaign
from vtl_japanese import timed_segments,patch_taps
from vtl_speech import sampa_segments

def render_timing(vtl, analysis, variant, seed):
    if variant == 'baseline':
        segments = sampa_segments(analysis['phonemes'], 0.85)
        pitch = []
        timing = []
    else:
        segments, pitch, timing = timed_segments(analysis)
    with tempfile.TemporaryDirectory(prefix='ans-ja-v2-') as temp:
        temp = Path(temp)
        seg = temp / 'text.seg'
        ges = temp / 'generated.ges'
        wav = temp / 'raw.wav'
        seg.write_text('\n'.join((f'name = {p}; duration_s = {d:.8f};' for p, d in segments)) + '\n')
        vtl.lib.vtlSegmentSequenceToGesturalScore.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_bool]
        vtl.lib.vtlGesturalScoreToAudio.argtypes = [ct.c_char_p, ct.c_char_p, ct.POINTER(ct.c_double), ct.POINTER(ct.c_int), ct.c_bool]
        vtl.check(vtl.lib.vtlSegmentSequenceToGesturalScore(str(seg).encode(), str(ges).encode(), False))
        tree = ET.parse(ges)
        root = tree.getroot()
        seq = root.find("gesture_sequence[@type='f0-gestures']")
        for g in list(seq):
            seq.remove(g)
        total = sum((d for _, d in segments))
        base = 12 * math.log2(160.0)
        if True:
            points = [(0.12 * total, -1.5), (0.48 * total, 1.0), (0.4 * total, -2.0)]
        else:
            points = [(d, 1.5 if high else -1.5) for d, high in pitch]
        for d, offset in points:
            ET.SubElement(seq, 'gesture', value=f'{base + offset:.8f}', slope='0', duration_s=f'{d:.8f}', time_constant_s='.025', neutral='0')
        taps = shift_taps(root, shift={'early':-.008,'late':.008}[variant])
        tree.write(ges, encoding='unicode')
        score = ges.read_text()
        ct.CDLL(None).srand(ct.c_uint(seed))
        vtl.check(vtl.lib.vtlGesturalScoreToAudio(str(ges).encode(), str(wav).encode(), None, None, False))
        fs, x = wavfile.read(wav)
        if fs != 44100:
            raise ValueError('VTL標本化周波数が想定と異なります')
        audio = signal.resample_poly(x.astype(float) / 32768, 80, 147) * 0.5
        fade = min(round(0.012 * 24000), len(audio) // 2)
        env = np.sin(np.linspace(0, np.pi / 2, fade)) ** 2
        audio[:fade] *= env
        audio[-fade:] *= env[::-1]
        return (audio, {'version': 'vtl-tap-timing-v1', 'variant': variant, 'phonemes': analysis['phonemes'], 'phrase_moras': analysis['phrases'], 'segments': segments, 'phone_times': timing, 'tap_gestures': taps, 'gestural_score_generated_at_runtime': score, 'f0_hz': 160, 'seed': seed, 'backend': vtl.metadata, 'limitations': ['短い舌尖閉鎖は弾音の研究近似。側方流路や実測接触は未校正', '非円唇uと無声化I/Uは未対応', '句内二値F0は辞書アクセント規則の近似であり自然韻律認定なし']}, 24000)


def shift_taps(root,shift):
    """元側音区間内で42ms閉鎖を最大8ms前後移動。周辺の総時間を保つ。"""
    seq=root.find("gesture_sequence[@type='tongue-tip-gestures']")
    count=0
    for g in list(seq):
        if 'lateral' not in g.get('value',''):continue
        total=float(g.get('duration_s'));width=min(.042,total)
        before=min(max((total-width)/2+shift,0.),total-width);after=total-before-width
        index=list(seq).index(g);seq.remove(g)
        replacements=[]
        for d,value,neutral in [(before,'',1),(width,'tt-alveolar-closure',0),(after,'',1)]:
            if d>1e-8:replacements.append(ET.Element('gesture',value=value,slope='0',duration_s=f'{d:.8f}',time_constant_s='.007',neutral=str(neutral)))
        for j,item in enumerate(replacements):seq.insert(index+j,item)
        count+=1
    return count

def main():
    parent=ROOT/'results/ans-vtl-calibrated-v3'
    config=read(ROOT/'config/campaign-v1.json')
    config.update(branch='42ms・7ms時定数を固定し、舌尖閉鎖指令を前後8msずらす',branch_sources={p:file_hash(ROOT/p) for p in ('vtl_tap_timing_v1.py','vtl_japanese.py','vtl_speech.py','cycle_campaign_v1.py','campaign_v2.py')})
    c=CycleCampaign('ans-vtl-tap-timing-v1',config)
    suite=read(parent/'task-suite.json');c.preflight_tasks(suite['tasks'])
    write_once(c.path/'task-suite.json',suite);write_once(c.path/'splits.json',read(parent/'splits.json'))
    write_once(c.path/'frozen-config.json',{'variants':{'early':-.008,'late':.008},'tap_width':.042,'tau':.007,'seeds':[41,43],
        'comparator':'ans-vtl-calibrated-v3/mora-tap-calibrated','protected_comparator':'ans-vtl-japanese-v2/mora',
        'task_count':12,'qualification':'内部の閉鎖と遷移を診断し、同じ12文のASRは補助比較に限る。最終参照は未開封。',
        'adoption_rule':'全体・開発8文・既使用新規4文のかなCERが両比較対象を悪化させないこと。E1/E2未資格のため品質昇格は禁止。'})
    vtl=VTL();results=[]
    try:
        for variant in ('early','late'):
            for task in suite['tasks']:
                for seed in (41,43):
                    row=c.trial(variant,'vtl','P4',task,seed,{'variant':variant,'shift_seconds':-.008 if variant=='early' else .008},
                        lambda t=task,v=variant,s=seed:render_timing(vtl,t['analysis'],v,s),save=seed==41)
                    results.append({'variant':variant,'task':task['id'],'kind':'sentence','seed':seed,'trial_id':row['trial_id'],'evaluation':row['evaluation'],'wav':row.get('wav')})
                print(variant,task['id'],flush=True)
        write_once(c.path/'p34-speech.json',{'rows':results,'status':'diagnostic-only'})
        write_once(c.path/'decision.json',{'state':'inconclusive','quality_goal_achieved':False,'renders':len(results),'E0_failed':sum(not r['evaluation']['E0_pass'] for r in results),'reason':'接触時刻の機構比較。E1/E2の資格は未取得。'})
    finally:vtl.close();c.close()

if __name__=='__main__':main()
