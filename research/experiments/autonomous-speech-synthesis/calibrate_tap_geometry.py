#!/usr/bin/env python3
"""録音も音声レンダーも使わず、閉鎖指令の長さと応答速度を校正する。"""
import ctypes as ct
import json
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT))
from autonomous_speech_synthesis.backends import VTL
from autonomous_speech_synthesis.io import read,write_once,file_hash
from vtl_japanese import patch_taps


def geometry(vtl,score,intervals):
    with tempfile.TemporaryDirectory(prefix='ans-calibrate-') as tmp:
        ges=Path(tmp)/'score.ges';seq=Path(tmp)/'tract.txt';ges.write_text(score)
        vtl.check(vtl.lib.vtlGesturalScoreToTractSequence(str(ges).encode(),str(seq).encode()))
        lines=[l for l in seq.read_text().splitlines() if l and not l.startswith('#')]
        count=int(lines[1]);tract=np.array([[float(x) for x in lines[3+2*i].split()] for i in range(count)])
    result=[]
    for start,end in intervals:
        frames=[]
        for index in range(max(0,int((start-.02)*44100/110)),min(count,int((end+.06)*44100/110)+1)):
            params=(ct.c_double*vtl.ntract)(*tract[index]);lengths=(ct.c_double*vtl.ntube)();areas=(ct.c_double*vtl.ntube)();art=(ct.c_int*vtl.ntube)();inc=ct.c_double();side=ct.c_double();velum=ct.c_double()
            vtl.check(vtl.lib.vtlTractToTube(params,lengths,areas,art,ct.byref(inc),ct.byref(side),ct.byref(velum)))
            center=np.cumsum(np.array(lengths))-.5*np.array(lengths);zone=(center>=inc.value-3)&(center<=inc.value)
            frames.append({'seconds':index*110/44100,'area_cm2':float(np.min(np.array(areas)[zone]))})
        closed=[f for f in frames if f['area_cm2']<=.01]
        result.append({'start':start,'end':end,'minimum_area_cm2':min(f['area_cm2'] for f in frames),'near_closure_seconds':len(closed)*110/44100,'near_closure':bool(closed),'frames':frames})
    return result


def main():
    output=ROOT/'results/tap-calibration-v1';output.mkdir(exist_ok=True)
    settings=[{'duration':d,'tau':tau} for d in (.028,.042,.056) for tau in (.005,.007,.012)]
    write_once(output/'frozen-config.json',{'settings':settings,'source_sha256':file_hash(Path(__file__)),'predeclared_selection':'全8文脈で断面0.01cm2以下へ到達し、閉鎖時間は各40ms以下。通過内で指令時間最小、時定数最大を優先。達しなければ音声候補へ昇格しない。','scope':'物理モデル内の機構のみ。知覚・日本語資格ではない。','audio_renders':0})
    path=ROOT/'results/ans-vtl-japanese-v2'
    controls=[(r['task'],read((path/r['wav']).with_suffix('.controls.json'))) for r in read(path/'p34-speech.json')['rows'] if r['variant']=='accent' and r.get('wav')]
    vtl=VTL();pointer=ct.POINTER(ct.c_double)
    vtl.lib.vtlGesturalScoreToTractSequence.argtypes=[ct.c_char_p,ct.c_char_p]
    vtl.lib.vtlTractToTube.argtypes=[pointer,pointer,pointer,ct.POINTER(ct.c_int),pointer,pointer,pointer]
    settings_results=[]
    try:
        for cfg in settings:
            data=[]
            for task,control in controls:
                root=ET.fromstring(control['gestural_score_generated_at_runtime'])
                if not patch_taps(root,cfg['duration']):continue
                sequence=root.find("gesture_sequence[@type='tongue-tip-gestures']");t=0;intervals=[]
                for g in sequence:
                    d=float(g.get('duration_s'))
                    if g.get('time_constant_s')=='0.007':g.set('time_constant_s',str(cfg['tau']))
                    if g.get('value')=='tt-alveolar-closure' and abs(d-cfg['duration'])<1e-6:intervals.append((t,t+d))
                    t+=d
                data.extend({'task':task,**r} for r in geometry(vtl,ET.tostring(root,encoding='unicode'),intervals))
            passed=len(data)==8 and all(r['near_closure'] and r['near_closure_seconds']<=.04 for r in data)
            row={'setting':cfg,'count':len(data),'near_closure_count':sum(r['near_closure'] for r in data),'passed':passed,'rows':data}
            settings_results.append(row);print(cfg,row['near_closure_count'],passed,flush=True)
    finally:vtl.close()
    viable=[r for r in settings_results if r['passed']]
    chosen=min(viable,key=lambda r:(r['setting']['duration'],-r['setting']['tau']))['setting'] if viable else None
    write_once(output/'calibration.json',{'settings':settings_results,'chosen':chosen,'quality_goal_achieved':False,'scope':'内部断面応答の校正。録音非使用、音声未生成。','source_sha256':file_hash(Path(__file__))})


if __name__=='__main__':main()
