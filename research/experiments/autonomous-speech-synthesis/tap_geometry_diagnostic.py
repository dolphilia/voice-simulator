#!/usr/bin/env python3
"""保存済みジェスチャから声道断面を再計算し、短い閉鎖の成立を調べる。"""
import ctypes as ct
import json
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.backends import VTL
from autonomous_speech_synthesis.io import read,write_once,file_hash


def main():
    path=ROOT/'results/ans-vtl-japanese-v2'
    outputs=read(path/'p34-speech.json')['rows'];files={(r['task'],r['variant']):path/r['wav'] for r in outputs if r.get('wav')}
    vtl=VTL();results=[]
    pointer=ct.POINTER(ct.c_double)
    vtl.lib.vtlGesturalScoreToTractSequence.argtypes=[ct.c_char_p,ct.c_char_p]
    vtl.lib.vtlTractToTube.argtypes=[pointer,pointer,pointer,ct.POINTER(ct.c_int),pointer,pointer,pointer]
    try:
        for (task,variant),wav in files.items():
            if variant!='accent-tap':continue
            score=read(wav.with_suffix('.controls.json'))['gestural_score_generated_at_runtime']
            tree=ET.fromstring(score);t=0;taps=[]
            for g in tree.find("gesture_sequence[@type='tongue-tip-gestures']"):
                d=float(g.get('duration_s'))
                if g.get('value')=='tt-alveolar-closure' and abs(d-.028)<1e-6:taps.append((t,t+d))
                t+=d
            if not taps:continue
            for kind in ('accent','accent-tap'):
                control=read(files[(task,kind)].with_suffix('.controls.json'))
                with tempfile.TemporaryDirectory(prefix='ans-geometry-') as tmp:
                    ges=Path(tmp)/'score.ges';seq=Path(tmp)/'tract.txt';ges.write_text(control['gestural_score_generated_at_runtime'])
                    vtl.check(vtl.lib.vtlGesturalScoreToTractSequence(str(ges).encode(),str(seq).encode()))
                    lines=[l for l in seq.read_text().splitlines() if l and not l.startswith('#')]
                    count=int(lines[1]);assert len(lines)==2+2*count
                    tract=np.array([[float(x) for x in lines[3+2*i].split()] for i in range(count)])
                for start,end in taps:
                    rows=[]
                    for index in range(max(0,int((start-.01)*44100/110)),min(count,int((end+.04)*44100/110)+1)):
                        params=(ct.c_double*vtl.ntract)(*tract[index]);lengths=(ct.c_double*vtl.ntube)();areas=(ct.c_double*vtl.ntube)();art=(ct.c_int*vtl.ntube)();inc=ct.c_double();side=ct.c_double();velum=ct.c_double()
                        vtl.check(vtl.lib.vtlTractToTube(params,lengths,areas,art,ct.byref(inc),ct.byref(side),ct.byref(velum)))
                        center=np.cumsum(np.array(lengths))-.5*np.array(lengths);zone=(center>=inc.value-3)&(center<=inc.value)
                        rows.append({'seconds':index*110/44100,'alveolar_min_area_cm2':float(np.min(np.array(areas)[zone])),'tongue_tip_side_elevation':side.value})
                    results.append({'task':task,'variant':kind,'command_start':start,'command_end':end,'minimum_area_cm2':min(r['alveolar_min_area_cm2'] for r in rows),'duration_below_001cm2':sum(r['alveolar_min_area_cm2']<=.01 for r in rows)*110/44100,'frames':rows})
    finally:vtl.close()
    tap=[r for r in results if r['variant']=='accent-tap'];base=[r for r in results if r['variant']=='accent']
    result={'status':'diagnostic-only','source_sha256':file_hash(Path(__file__)),'sample_step_seconds':110/44100,'area_region':'切歯位置の0〜3cm後方の管区間','near_closure_threshold_cm2':.01,'tap_near_closure_count':sum(r['minimum_area_cm2']<=.01 for r in tap),'parent_near_closure_count':sum(r['minimum_area_cm2']<=.01 for r in base),'tap_count':len(tap),'rows':results,'scope':'VTL内部の幾何診断。実際の日本語弾音や知覚の合否ではない。録音参照は使用しない。'}
    write_once(path/'tap-geometry-diagnostic.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
