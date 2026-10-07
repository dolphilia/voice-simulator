#!/usr/bin/env python3
"""制御ログの予定と実波形の音素内エネルギーを照合する。"""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy import signal

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"src"))
from autonomous_speech_synthesis.io import read,write_once,file_hash
from autonomous_speech_synthesis.evaluation import estimate_f0


def inspect(audio,fs,events):
    rows=[]
    for event in events:
        a=round(event["start_seconds"]*fs);b=round(event["end_seconds"]*fs)
        trim=max(1,min((b-a)//5,round(.01*fs)))
        x=audio[a+trim:b-trim]
        if not len(x):continue
        rms=float(np.sqrt(np.mean(x*x)))
        f,p=signal.welch(x,fs,nperseg=min(512,len(x)))
        hi=float(np.sum(p[f>3000])/max(np.sum(p),1e-30))
        f0,confidence=estimate_f0(x,fs)
        expected_voiced=event["phone"] in "aeo" or (event["phone"] in ("i","u") and event.get("voiced_target",1)>.5)
        rows.append({**event,"rms":rms,"high_band_fraction":hi,"f0_hz":f0,"f0_confidence":confidence,
                     "expected_voiced_vowel":expected_voiced,"voiced_vowel_missing":expected_voiced and rms<1e-4,
                     "closure_or_noise_note":"音素区間の診断値。VOTの正確な推定値ではない"})
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--campaign",default="ans-pilot-v1");args=parser.parse_args()
    path=ROOT/"results"/args.campaign
    rows=[];fixture=[]
    for sample in read(path/"p34-speech.json")["rows"]:
        if not sample.get("wav"):continue
        wav=path/sample["wav"];fs,x=wavfile.read(wav);log=read(wav.with_suffix(".controls.json"))
        if "events" not in log:continue
        values=inspect(x,fs,log["events"])
        rows.append({"task":sample["task"],"kind":sample["kind"],"events":values,"any_missing":any(v["voiced_vowel_missing"] for v in values)})
        if len(fixture)<5:
            for event in log["events"]:
                if event["phone"] in ("a","e","o"):
                    broken=x.copy();a=round(event["start_seconds"]*fs);b=round(event["end_seconds"]*fs);broken[a:b]=0.
                    detected=any(v["voiced_vowel_missing"] for v in inspect(broken,fs,log["events"]))
                    fixture.append({"task":sample["task"],"dropped_phone":event["phone"],"detected":detected});break
    result={"status":"diagnostic-only","script_sha256":file_hash(Path(__file__)),"threshold_rms":.0001,"source":"相対振幅の完全欠落検出用。自然さの閾値ではない",
            "rows":rows,"utterances_with_missing_vowels":sum(r["any_missing"] for r in rows),"dropout_fixtures":fixture,"all_dropout_fixtures_detected":bool(fixture) and all(f["detected"] for f in fixture),
            "limitations":["制御ログは生成器由来。独立認識器の代わりにはならない","閉鎖・破裂・摩擦帯域を記録するが、音素同定とVOTの資格は付与しない"]}
    write_once(path/"mechanism-diagnostic.json",result)
    print(json.dumps({k:v for k,v in result.items() if k not in ("rows","dropout_fixtures")},ensure_ascii=False))


if __name__=="__main__":main()
