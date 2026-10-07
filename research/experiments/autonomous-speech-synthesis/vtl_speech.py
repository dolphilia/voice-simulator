#!/usr/bin/env python3
"""登録済みVTL構造を音素列へ拡張する独立の機構診断campaign。"""
import argparse
import ctypes as ct
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
import numpy as np
from scipy.io import wavfile
from scipy import signal

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"src"))
from autonomous_speech_synthesis.io import read,write_once,file_hash,digest
from autonomous_speech_synthesis.backends import VTL
from autonomous_speech_synthesis.runner import Campaign
from autonomous_speech_synthesis.gestures import kana_to_phonemes


def sampa_segments(phones,speed):
    mapping={"sh":"S","ch":"tS","j":"dZ","y":"j","w":"u","r":"l","N":"N","I":"i","U":"u","pau":""}
    supported=set("aiueo")|{"m","n","s","h","f","p","t","k","b","d","g","z","ts"}
    output=[("",.05)]
    for i,p in enumerate(phones):
        if p=="Q":
            next_phone=phones[i+1] if i+1<len(phones) else None
            if next_phone not in ("p","t","k","s","sh","ch","ts"):
                raise ValueError("この促音文脈はVTL前段で未対応です")
            output.append((mapping.get(next_phone,next_phone),.10/speed));continue
        duration=(.12 if p.lower() in "aiueo" else .14 if p=="pau" else .10 if p=="N" else .065)/speed
        if p in ("ky","gy","ny","hy","my","ry"):
            base={"ky":"k","gy":"g","ny":"n","hy":"h","my":"m","ry":"l"}[p]
            output.extend([(base,duration*.55),("j",duration*.45)])
        elif p in mapping or p in supported:output.append((mapping.get(p,p),duration))
        else:raise ValueError(f"VTL写像の未対応音素: {p}")
    output.append(("",.1))
    return output


def render_vtl(vtl,phones,f0=220,speed=1.,seed=11,flat=False):
    segments=sampa_segments(phones,speed)
    with tempfile.TemporaryDirectory(prefix="ans-vtl-") as tmp:
        tmp=Path(tmp);seg=tmp/"input.seg";ges=tmp/"generated.ges";wav=tmp/"raw.wav"
        seg.write_text("\n".join(f"name = {p}; duration_s = {d:.8f};" for p,d in segments)+"\n")
        vtl.lib.vtlSegmentSequenceToGesturalScore.argtypes=[ct.c_char_p,ct.c_char_p,ct.c_bool]
        vtl.lib.vtlGesturalScoreToAudio.argtypes=[ct.c_char_p,ct.c_char_p,ct.POINTER(ct.c_double),ct.POINTER(ct.c_int),ct.c_bool]
        vtl.check(vtl.lib.vtlSegmentSequenceToGesturalScore(str(seg).encode(),str(ges).encode(),False))
        root=ET.parse(ges)
        f0seq=root.getroot().find("gesture_sequence[@type='f0-gestures']")
        total=sum(d for _,d in segments)
        for child in list(f0seq):f0seq.remove(child)
        base_st=12*math.log2(f0)
        fractions=[(.12,-1.5),(.48,1.0),(.40,-2.0)] if not flat else [(1.,0.)]
        for fraction,offset in fractions:
            ET.SubElement(f0seq,"gesture",value=f"{base_st+offset:.6f}",slope="0",duration_s=f"{total*fraction:.8f}",time_constant_s="0.025",neutral="0")
        root.write(ges,encoding="unicode")
        score=ges.read_text()
        ct.CDLL(None).srand(ct.c_uint(seed))
        vtl.check(vtl.lib.vtlGesturalScoreToAudio(str(ges).encode(),str(wav).encode(),None,None,False))
        fs,raw=wavfile.read(wav)
        audio=raw.astype(float)/(32768 if raw.dtype==np.int16 else 1.)
        audio=signal.resample_poly(audio,80,147)*.5
        fade=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,fade))**2
        audio[:fade]*=env;audio[-fade:]*=env[::-1]
        return audio,{"version":"vtl-jd3-gesture-v1","phonemes":phones,"segments":segments,"gestural_score_generated_at_runtime":score,
                      "f0_hz":f0,"speed":speed,"seed":seed,"flat":flat,"backend":vtl.metadata,
                      "known_mapping_limitations":["rはlで近似。日本語弾音の合格認定なし","u/w、撥音N、口蓋化はドイツ語標的による近似","無声化I/Uは母音へ写像、適格性は未確認"]},24000


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--campaign",default="ans-vtl-speech-v1");parser.add_argument("--base",default="ans-pilot-v1");parser.add_argument("--smoke",action="store_true");args=parser.parse_args()
    if args.smoke:
        from autonomous_speech_synthesis.evaluation import evaluate
        import time
        vtl=VTL();start=time.monotonic()
        try:
            x,log,fs=render_vtl(vtl,kana_to_phonemes("あおいそら"))
            print(json.dumps({"evaluation":evaluate(x,{},fs),"seconds":time.monotonic()-start,"duration":len(x)/fs},ensure_ascii=False))
        finally:vtl.close()
        return
    config=read(ROOT/"config/campaign-v1.json")
    config.update(branch="P2でVTLの帯域残差がDSPより小さいため、同構造を音素列へ拡張する機構診断",branch_source_sha256=file_hash(Path(__file__)),model_version="vtl-jd3-gesture-v1")
    campaign=Campaign(args.campaign,config)
    vtl=VTL()
    try:
        base=ROOT/"results"/args.base
        write_once(campaign.path/"model-registry.json",{"id":"vtl-jd3-gesture-v1","parent":"vtl-jd3-v1","source_sha256":file_hash(Path(__file__)),"scope":"日本語音素をドイツ語標的へ近似写像する研究用。品質未資格","neural_runtime":False,"recorded_source":False})
        suite=read(base/"task-suite.json")
        write_once(campaign.path/"task-suite.json",suite)
        write_once(campaign.path/"splits.json",read(base/"splits.json"))
        tasks=[t for t in suite["tasks"] if t["stage"]=="P4"]
        # 主要系列を一つずつ含むCV。段階的な拡張の能力診断。
        tasks += [t for t in suite["tasks"] if t["kind"]=="consonant" and t["id"].startswith("CV-") and t["id"].endswith("-a")]
        write_once(campaign.path/"frozen-config.json",{"task_ids":[t["id"] for t in tasks],"seeds":[41,43],"variants":["gesture-prosody","flat-prosody"],"f0_hz":220,"speed":1.,"score_for_selection":None,"confirmation_reference_opened":False})
        results=[]
        for variant in ("gesture-prosody","flat-prosody"):
            for task in tasks:
                if variant=="flat-prosody" and task["kind"]!="sentence":continue
                for seed in (41,43):
                    result=campaign.trial(variant,"vtl",task["stage"],task,seed,{"f0_hz":220,"speed":1.,"flat":variant=="flat-prosody"},
                        lambda t=task,s=seed,v=variant:render_vtl(vtl,t["phonemes"],seed=s,flat=v=="flat-prosody"),save=seed==41)
                    results.append({"variant":variant,"task":task["id"],"kind":task["kind"],"family":task.get("family"),"seed":seed,"trial_id":result["trial_id"],"evaluation":result["evaluation"],"wav":result.get("wav")})
                print("VTL",variant,task["id"],flush=True)
        write_once(campaign.path/"p34-speech.json",{"rows":results,"quality_status":"inconclusive","backend":"vtl","known_limits":"日本語弾音・無声化・非円唇uは未対応近似"})
        write_once(campaign.path/"decision.json",{"state":"inconclusive","quality_goal_achieved":False,"render_count":len(results),"E0_failed":sum(not r["evaluation"]["E0_pass"] for r in results),"reason":"VTL音素写像の機構検査。日本語知覚資格なし"})
    finally:vtl.close();campaign.close()


if __name__=="__main__":main()
