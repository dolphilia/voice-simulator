#!/usr/bin/env python3
"""VTLのF0標的と舌尖接触を保存波形から点検する。"""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import numpy as np
from scipy.io import wavfile
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,file_hash
from autonomous_speech_synthesis.evaluation import estimate_f0


def main():
    path=ROOT/'results/ans-vtl-japanese-v2'
    rows=read(path/'p34-speech.json')['rows'];f0rows=[];taps=[]
    files={(r['task'],r['variant']):path/r['wav'] for r in rows if r.get('wav')}
    for (task,variant),wav in files.items():
        if variant not in ('accent','accent-tap'):continue
        fs,x=wavfile.read(wav);controls=read(wav.with_suffix('.controls.json'))
        tree=ET.fromstring(controls['gestural_score_generated_at_runtime']);t=0
        for i,g in enumerate(tree.find("gesture_sequence[@type='f0-gestures']")):
            duration=float(g.get('duration_s'));end=t+duration
            if duration>=.18:
                # 立上がりを避けた60msの窓。無声区間は欠測として残す。
                lo,hi=round((end-.075)*fs),round((end-.015)*fs)
                f0,conf=estimate_f0(x[lo:hi],fs)
                target=2**(float(g.get('value'))/12)
                f0rows.append({'task':task,'variant':variant,'gesture':i,'target_hz':target,'measured_hz':f0,'confidence':conf,'relative_error':abs(f0/target-1) if f0 is not None else None,'usable':f0 is not None and conf>=.65})
            t=end
        if variant=='accent-tap':
            _,base=wavfile.read(files[(task,'accent')]);t=0
            for g in tree.find("gesture_sequence[@type='tongue-tip-gestures']"):
                duration=float(g.get('duration_s'))
                if g.get('value')=='tt-alveolar-closure' and abs(duration-.028)<1e-6:
                    # 接触指令の後半から14ms後までを両条件同一時刻で比較。
                    lo,hi=round((t+duration/2)*fs),round((t+duration+.014)*fs)
                    before=float(np.sqrt(np.mean(base[lo:hi]**2)));after=float(np.sqrt(np.mean(x[lo:hi]**2)))
                    taps.append({'task':task,'start_seconds':t,'duration_seconds':duration,'parent_rms':before,'tap_rms':after,'ratio':after/max(before,1e-10)})
                t+=duration
    usable=[r for r in f0rows if r['usable']]
    summary={'status':'diagnostic-only','promotion_allowed':False,'source_sha256':file_hash(Path(__file__)),
      'f0':{'attempts':len(f0rows),'usable':len(usable),'missing_or_uncertain':len(f0rows)-len(usable),'median_relative_error':float(np.median([r['relative_error'] for r in usable])),'within_5_percent':sum(r['relative_error']<=.05 for r in usable),'rows':f0rows},
      'tap':{'count':len(taps),'lower_rms_count':sum(r['ratio']<1 for r in taps),'median_rms_ratio':float(np.median([r['ratio'] for r in taps])),'rows':taps},
      'scope':'信号上の標的追従と接触指令の差。日本語アクセントの正答や弾音知覚の証明ではない。'}
    write_once(path/'prosody-diagnostic.json',summary)
    print(json.dumps({k:{a:b for a,b in v.items() if a!='rows'} if isinstance(v,dict) else v for k,v in summary.items()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
