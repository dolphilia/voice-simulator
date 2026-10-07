#!/usr/bin/env python3
"""幾何校正した短い舌尖閉鎖だけを比較する第6campaign。"""
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
from campaign_v2 import BoundedCampaign
from vtl_japanese import timed_segments,patch_taps
from vtl_speech import sampa_segments

def render_calibrated(vtl, analysis, variant, seed):
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
        if variant == 'mora-tap-calibrated':
            points = [(0.12 * total, -1.5), (0.48 * total, 1.0), (0.4 * total, -2.0)]
        else:
            points = [(d, 1.5 if high else -1.5) for d, high in pitch]
        for d, offset in points:
            ET.SubElement(seq, 'gesture', value=f'{base + offset:.8f}', slope='0', duration_s=f'{d:.8f}', time_constant_s='.025', neutral='0')
        taps = patch_taps(root, duration=0.042)
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
        return (audio, {'version': 'vtl-japanese-gesture-v3', 'variant': variant, 'phonemes': analysis['phonemes'], 'phrase_moras': analysis['phrases'], 'segments': segments, 'phone_times': timing, 'tap_gestures': taps, 'gestural_score_generated_at_runtime': score, 'f0_hz': 160, 'seed': seed, 'backend': vtl.metadata, 'limitations': ['短い舌尖閉鎖は弾音の研究近似。側方流路や実測接触は未校正', '非円唇uと無声化I/Uは未対応', '句内二値F0は辞書アクセント規則の近似であり自然韻律認定なし']}, 24000)

def main():
    parent=ROOT/'results/ans-vtl-japanese-v2'
    calibration=read(ROOT/'results/tap-calibration-v1/calibration.json')
    if calibration['chosen']!={'duration':.042,'tau':.007}:raise ValueError('事前条件を通過した幾何校正と一致しません')
    config=read(ROOT/'config/campaign-v1.json')
    config.update(branch='全8文脈の短い閉鎖が成立した42ms指令を、同じ音素・韻律条件で比較する',model_version='vtl-japanese-gesture-v3',branch_sources={p:file_hash(ROOT/p) for p in ('vtl_calibrated.py','vtl_japanese.py','campaign_v2.py','vtl_speech.py','calibrate_tap_geometry.py')})
    c=BoundedCampaign('ans-vtl-calibrated-v3',config)
    suite=read(parent/'task-suite.json');c.preflight_tasks(suite['tasks'])
    write_once(c.path/'task-suite.json',suite);write_once(c.path/'splits.json',read(parent/'splits.json'))
    write_once(c.path/'model-registry.json',{'id':'vtl-japanese-gesture-v3','parent':'vtl-japanese-gesture-v2','changes':['tap-command-28ms-to-42ms'],'calibration_sha256':file_hash(ROOT/'results/tap-calibration-v1/calibration.json'),'quality_adoption':False})
    write_once(c.path/'frozen-config.json',{'variants':['mora-tap-calibrated','accent-tap-calibrated'],'task_count':len(suite['tasks']),'seeds':[41,43],'tap_seconds':.042,'tau_seconds':.007,'comparators':{'mora-tap-calibrated':'ans-vtl-japanese-v2/mora','accent-tap-calibrated':'ans-vtl-japanese-v2/accent-tap'},'scope':'同じ12文の診断。最終品質確認群を使用しない。','total_cycle_campaign_limit':6})
    vtl=VTL();result=[]
    try:
        for variant in ('mora-tap-calibrated','accent-tap-calibrated'):
            for task in suite['tasks']:
                for seed in (41,43):
                    row=c.trial(variant,'vtl','P4',task,seed,{'variant':variant,'tap_seconds':.042,'tau_seconds':.007},lambda t=task,v=variant,s=seed:render_calibrated(vtl,t['analysis'],v,s),save=seed==41)
                    result.append({'variant':variant,'task':task['id'],'kind':'sentence','seed':seed,'trial_id':row['trial_id'],'evaluation':row['evaluation'],'wav':row.get('wav')})
                print(variant,task['id'],flush=True)
        write_once(c.path/'p34-speech.json',{'rows':result,'status':'diagnostic-only','quality_goal_achieved':False})
        write_once(c.path/'decision.json',{'state':'inconclusive','quality_goal_achieved':False,'renders':len(result),'E0_failed':sum(not r['evaluation']['E0_pass'] for r in result),'reason':'幾何校正の音声比較。独立E1/E2資格がなく最終品質を認定しない。'})
    finally:vtl.close();c.close()


if __name__=='__main__':main()
