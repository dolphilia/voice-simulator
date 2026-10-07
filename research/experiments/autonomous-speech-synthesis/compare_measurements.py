#!/usr/bin/env python3
"""探索後の共通レート監査。再選別・閾値調整には使わない。"""
import argparse
import json
import math
from pathlib import Path
import sys
import numpy as np
from scipy.io import wavfile
from scipy import signal

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"src"))
from autonomous_speech_synthesis.io import read,write_once,file_hash
from autonomous_speech_synthesis.evaluation import acoustic_features,grouped_bootstrap


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--campaign",default="ans-pilot-v1");args=parser.parse_args()
    path=ROOT/"results"/args.campaign
    search=read(path/"p2-search.json")
    selected={r["backend"]:r["candidate_id"] for r in search["chosen"]}
    measurements={};details=[]
    for p in sorted((path/"trials").glob("*.json")):
        trial=read(p)
        if trial["task"]["kind"]!="vowel" or not trial.get("wav"):continue
        backend=trial["backend"]
        if backend not in ("B9","G40") and (trial["stage"]!="P2-recheck" or trial["candidate_id"]!=selected.get(backend)):continue
        fs,x=wavfile.read(path/trial["wav"])
        divisor=math.gcd(fs,24000)
        x=signal.resample_poly(x,24000//divisor,fs//divisor) if fs!=24000 else x
        # 長さを揃えた中央280ms。全方式に同じ処理を適用する。
        mid=len(x)//2;half=round(.14*24000);x=x[mid-half:mid+half]
        measured=acoustic_features(x,24000)
        task=trial["task"]
        measurements[(backend,task["phonemes"][0],task["f0_hz"])]=measured
        details.append({"backend":backend,"vowel":task["phonemes"][0],"f0_hz":task["f0_hz"],"features":measured,"source_wave_sha256":file_hash(path/trial["wav"]),"trial_id":trial["trial_id"]})
    reference=read(path/"reference-selection.json")
    by_speaker={}
    for row in reference["rows"]:
        f0=row["features"]["f0_hz"]
        nearest=min((160,220,300),key=lambda f:abs(np.log(f/f0)))
        if abs(np.log(nearest/f0))>np.log(1.3):continue
        target=np.log10(np.maximum(row["features"]["band_energy_fractions"],1e-6))
        for backend in ("dsp","vtl","B9","G40"):
            m=measurements.get((backend,row["vowel"],nearest))
            if m:
                loss=float(np.mean((np.log10(np.maximum(m["band_energy_fractions"],1e-6))-target)**2))
                by_speaker.setdefault(row["speaker"],{}).setdefault(backend,[]).append(loss)
    means={s:{b:float(np.mean(v)) for b,v in data.items()} for s,data in by_speaker.items()}
    comparisons={}
    for backend in ("dsp","vtl"):
        differences=[m[backend]-m["G40"] for m in means.values() if backend in m and "G40" in m]
        comparisons[backend+"-minus-G40"]=grouped_bootstrap(differences,comparisons=2)
    result={"status":"diagnostic-only","script_sha256":file_hash(Path(__file__)),"sample_rate_hz":24000,"stable_region_seconds":.28,"phase":"探索後の測定差点検。候補・ゲートを変更しない", "reason":"最初の台帳ではB9/G40のみ48kHz、Welchの窓長が同じsample数だった。物理時間を揃えた監査を別保存する。",
            "measurements":details,"selection_speaker_means":means,"cluster_bootstrap":comparisons,"noninferiority_margin":None,"promotion_allowed":False,"speaker_generalization_claim":False}
    write_once(path/"common-measurement-audit.json",result)
    print(json.dumps({"selection_speaker_means":means,"cluster_bootstrap":comparisons},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
