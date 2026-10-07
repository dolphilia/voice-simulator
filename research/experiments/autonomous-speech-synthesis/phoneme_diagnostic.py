#!/usr/bin/env python3
"""ASRとは別系統の音響音素診断。自動境界のラベルを正解認定しない。"""
import argparse
import json
from pathlib import Path
import sys
from collections import Counter
import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"src"))
from autonomous_speech_synthesis.io import read,write_once,file_hash,REPO


def features(x,fs):
    x=np.asarray(x,dtype=float);x=x-np.mean(x)
    rms=np.sqrt(np.mean(x*x))
    freq,power=signal.welch(x,fs,nperseg=min(len(x),512))
    power/=max(np.sum(power),1e-30)
    bands=[np.sum(power[(freq>=lo)&(freq<hi)]) for lo,hi in [(0,400),(400,800),(800,1500),(1500,2500),(2500,4000),(4000,8000)]]
    ac=signal.correlate(x,x,mode="full",method="fft")[len(x)-1:]
    periodic=np.max(ac[int(fs/450):min(len(ac),int(fs/70))])/max(ac[0],1e-30) if len(ac)>fs/450 else 0.
    return np.r_[np.log10(np.maximum(bands,1e-5)),periodic,np.mean(np.diff(np.signbit(x))!=0)]


def load_reference(splits,group):
    rows=[];excluded=Counter()
    for r in splits["groups"][group]["records"]:
        wav=REPO/r["wav"];lab=REPO/r["lab"]
        if file_hash(wav)!=r["sha256"] or file_hash(lab)!=r["label_sha256"]:raise ValueError("参照ハッシュ不一致")
        fs,x=wavfile.read(wav);x=x.astype(float)/32768
        for index,line in enumerate(lab.read_text().splitlines()):
            start,end,phone=line.split();start=float(start);end=float(end)
            if phone in ("sil","pau"):continue
            if end-start<.045:excluded["too-short"]+=1;continue
            variants=[]
            for delta in (-.01,0,.01):
                a=round(max(0,start+delta)*fs);b=min(len(x),round((end+delta)*fs))
                variants.append(features(x[a:b],fs))
            rows.append({"speaker":r["speaker"],"sentence":r["sentence"],"phone":phone,"features":np.array(variants),"segment":index})
    return rows,dict(excluded)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--campaign",default="ans-pilot-v1");args=parser.parse_args()
    path=ROOT/"results"/args.campaign
    splits=read(path/"splits.json")
    dev,dev_excluded=load_reference(splits,"development");selection,sel_excluded=load_reference(splits,"selection")
    counts=Counter(r["phone"] for r in dev)
    labels=sorted(k for k,v in counts.items() if v>=5)
    means=np.array([np.mean([r["features"][1] for r in dev if r["phone"]==k],axis=0) for k in labels])
    scale=np.std([r["features"][1] for r in dev],axis=0)+.05
    def recognize(f):return labels[int(np.argmin(np.mean(((means-f)/scale)**2,axis=1)))]
    validation=[]
    for r in selection:
        pred=[recognize(f) for f in r["features"]]
        validation.append({"speaker":r["speaker"],"sentence":r["sentence"],"expected":r["phone"],"predicted":pred[1],"perturbation_stable":len(set(pred))==1,"in_training_inventory":r["phone"] in labels})
    generated=[]
    for row in read(path/"p34-speech.json")["rows"]:
        if row.get("wav") and row["kind"] in ("consonant","transition"):
            wav=path/row["wav"];fs,x=wavfile.read(wav)
            log=read(wav.with_suffix(".controls.json"))
            for event in log["events"]:
                a=round(event["start_seconds"]*fs);b=round(event["end_seconds"]*fs)
                generated.append({"task":row["task"],"expected":event["phone"],"predicted":recognize(features(x[a:b],fs)),"in_training_inventory":event["phone"] in labels})
    def summary(rows):
        matrix=Counter((r["expected"],r["predicted"]) for r in rows)
        return {"count":len(rows),"accuracy":sum(r["expected"]==r["predicted"] for r in rows)/len(rows) if rows else None,
                "out_of_inventory":sum(not r["in_training_inventory"] for r in rows),"confusion_matrix":[{"expected":a,"predicted":b,"count":n} for (a,b),n in sorted(matrix.items())]}
    result={"status":"diagnostic-only","promotion_allowed":False,"method":"非学習帯域特徴から開発参照の音素重心へ標準化距離。パラメータは研究側のみ。","script_sha256":file_hash(Path(__file__)),
            "reference_labels":"JVS自動alignment。人手正解を仮定しない","training_counts":dict(counts),"training_excluded":dev_excluded,"selection_excluded":sel_excluded,
            "selection":summary(validation),"generated":summary(generated),"selection_rows":validation,"generated_rows":generated,
            "selection_boundary_stability":sum(r["perturbation_stable"] for r in validation)/len(validation),"known_limitations":["音素平均特徴は閉鎖/破裂の時間順序を表さない","少数参照・低F0と高F0の差を完全に補正しない","ASRと同じSSL基盤を使わないが、知覚的明瞭性を認定できない"]}
    write_once(path/"phoneme-diagnostic.json",result)
    print(json.dumps({k:result[k] for k in ("status","selection_boundary_stability")},ensure_ascii=False))
    print("選別accuracy",result["selection"]["accuracy"],"生成accuracy",result["generated"]["accuracy"])


if __name__=="__main__":main()
